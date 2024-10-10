#!/usr/bin/env python3
"""This script provide much better flexibility in comparison to original
nm-openconnect plugin. It can automatically feed password on stdin and pass
form data in command line options as well.
"""

import logging
from argparse import ArgumentParser, Namespace
from enum import IntEnum
from functools import wraps
from json import dumps
from logging.handlers import SysLogHandler
from os import getenv
from subprocess import PIPE, Popen, TimeoutExpired
from typing import Any, Optional

import dbus
import dbus.mainloop.glib
import dbus.service
from dbus.service import method, signal
from gi.repository import GLib

NM_DBUS_SERVICE_OPENCONNECT = 'org.freedesktop.NetworkManager.openconnect'
NM_DBUS_INTERFACE = 'org.freedesktop.NetworkManager.VPN.Plugin'
NM_DBUS_PATH = '/org/freedesktop/NetworkManager/VPN/Plugin'

NM_VPN_LOG_LEVEL = getenv('NM_VPN_LOG_LEVEL', '0')
NM_VPN_LOG_SYSLOG = getenv('NM_VPN_LOG_SYSLOG', '1')

parser = ArgumentParser()
parser.add_argument('--bus-name', default=NM_DBUS_SERVICE_OPENCONNECT,
                    help='D-Bus name to use for this instance')
parser.add_argument('--persist', default=False, action='store_true',
                    help='don’t quit when VPN connection terminates')
parser.add_argument('--debug', default=False, action='store_true',
                    help='enable verbose debug logging (may expose passwords)')


def trace(fn):
    @wraps(fn)
    def traced(self, *args, **kwargs):
        logger.info('nm-oc: %s(%s, %s)', fn.__name__, args, kwargs)
        return fn(self, *args, **kwargs)
    return traced


def convert(obj):
    if isinstance(obj, dbus.Dictionary):
        return {str(k): convert(v) for k, v in obj.items()}
    elif isinstance(obj, dbus.Array):
        return [convert(el) for el in obj]
    elif isinstance(obj, dbus.String):
        return str(obj)
    elif isinstance(obj, dbus.UInt16 | dbus.UInt32 | dbus.UInt64):
        return int(obj)
    elif isinstance(obj, dbus.Int16 | dbus.Int32 | dbus.Int64):
        return int(obj)
    elif isinstance(obj, dbus.Boolean):
        return bool(obj)
    else:
        return obj


class ServiceState(IntEnum):

    Unknown = 0

    Init = 1

    Shutdown = 2

    Starting = 3

    Started = 4

    Stoping = 5

    Stopped = 6


class InteractiveNotSupportedError(dbus.DBusException):

    _dbus_error_name = \
        'org.freedesktop.NetworkManager.VPN.Error.InteractiveNotSupported'


class Plugin(dbus.service.Object):

    def __init__(self, loop, conn=None, object_path=None, bus_name=None):
        super().__init__(conn=conn, object_path=object_path, bus_name=bus_name)
        self.bus_name = bus_name.get_name()
        self.config = {}
        self.ip4config = {}
        self.proc: Optional[Popen] = None
        self.loop = loop

        self.gateway: Optional[str] = None
        self.password: Optional[str] = None
        self.username: Optional[str] = None
        self.protocol: Optional[str] = None
        self.form_data: list[str] = []

    def run(self):
        self.loop.run()

    @method(dbus_interface=NM_DBUS_INTERFACE,
            in_signature='a{sa{sv}}',
            out_signature='')
    def Connect(self, connection: dict[str, dict[str, Any]]):
        # TODO(@daskol): What config we should use?
        connection = convert(connection)
        logger.info('nm-oc: Connect(%s)', connection)

        env = {'NM_DBUS_SERVICE_OPENCONNECT': self.bus_name}  # Helper script.
        cmd = [
            'openconnect', '-u', self.username, '--passwd-on-stdin',
            '--script', '/usr/lib/nm-openconnect-service-openconnect-helper',
            '--syslog', '--protocol', self.protocol, *self.form_data,
            self.gateway
        ]
        logger.info('command to connect: %s', dumps(cmd, ensure_ascii=False))
        self.StateChanged(ServiceState.Starting)
        self.proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
        try:
            input = f'{self.password}\n'.encode('utf-8')
            outs, errs = self.proc.communicate(input, timeout=5.0)
            logger.info('connected to %s: stdout: %s; stderr: %s',
                        self.gateway, outs, errs)
        except TimeoutExpired:
            logger.info('communication timed out')
        except Exception:
            self.proc.kill()
            outs, errs = self.proc.communicate()
            logger.info('stdout: %s\nstderr: %s', outs, errs)

    @method(dbus_interface=NM_DBUS_INTERFACE,
            in_signature='a{sa{sv}}a{sv}')
    @trace
    def ConnectInteractive(self, connection: dict[str, dict[str, Any]],
                           details: list[Any]):
        raise InteractiveNotSupportedError

    @method(dbus_interface=NM_DBUS_INTERFACE,
            in_signature='a{sa{sv}}',
            out_signature='s')
    @trace
    def NeedSecrets(self, settings: dict[str, dict[str, Any]]) -> str:
        vpn = settings.get('vpn', {})
        data = vpn.get('data', {})
        self.username = data.get('username')
        self.protocol = data.get('protocol')
        self.gateway = data.get('gateway')

        # Parse form data to command line terms.
        form_data = []
        for field in data.get('form', '').split(','):
            if field:
                form_data.extend(['-F', field])
        if form_data:
            self.form_data = form_data

        # Set or update password.
        secrets = vpn.get('secrets', {})
        if (password := secrets.get('password')):
            self.password = password

        section = ''  # Secret section?
        if self.password is None:
            section = 'vpn'
        return section

    @method(dbus_interface=NM_DBUS_INTERFACE)
    @trace
    def Disconnect(self):
        if self.proc is None:
            logger.info('openconnect binary has not been run: skipping it')
        else:
            self.proc.kill()
            self.proc.wait()
            logger.info('exit code of openconnect binary is %d',
                        self.proc.returncode)

        logger.info('send stop signal to event loop')
        self.loop.quit()

    @method(dbus_interface=NM_DBUS_INTERFACE, in_signature='a{sv}')
    @trace
    def SetConfig(self, config: dict[str, Any]):
        self.config = {}
        for key in ('banner', 'tundev', 'gateway', 'mtu'):
            if (val := config.get('banner')) is not None:
                self.config['banner'] = val
        self.Config(config)

    @method(dbus_interface=NM_DBUS_INTERFACE, in_signature='a{sv}')
    @trace
    def SetIp4Config(self, config: dict[str, Any]):
        self.ip4config = {str(k): v for k, v in config.items()}
        self.Ip4Config({**self.config, **self.ip4config})
        self.StateChanged(ServiceState.Started)

    @method(dbus_interface=NM_DBUS_INTERFACE, in_signature='a{sv}')
    @trace
    def SetIp6Config(self, config: dict[str, Any]):
        pass

    @method(dbus_interface=NM_DBUS_INTERFACE, in_signature='s')
    @trace
    def SetFailure(self, reason: str):
        pass

    @method(dbus_interface=NM_DBUS_INTERFACE, in_signature='a{sa{sv}}')
    @trace
    def NewSecrets(self, connection: dict[str, dict[str, Any]]):
        pass

    @signal(dbus_interface=NM_DBUS_INTERFACE, signature='u')
    @trace
    def StateChanged(self, state: int):
        pass

    @signal(dbus_interface=NM_DBUS_INTERFACE, signature='a{sv}')
    @trace
    def Config(self, config: dict[str, Any]):
        config = convert(config)
        logger.info('config: %s', dumps(config, ensure_ascii=False))

    @signal(dbus_interface=NM_DBUS_INTERFACE, signature='a{sv}')
    @trace
    def Ip4Config(self, ip4config: dict[str, Any]):
        ip4config = convert(ip4config)
        logger.info('ip4config: %s', dumps(ip4config, ensure_ascii=False))

    @signal(dbus_interface=NM_DBUS_INTERFACE, signature='a{sv}')
    @trace
    def Ip6Config(self, ip6config: dict[str, Any]):
        ip6config = convert(ip6config)
        logger.info('ip6config: %s', dumps(ip6config, ensure_ascii=False))


class OpenConnectPlugin(dbus.service.Object):

    pass


def run(ns: Namespace):
    bus_loop = dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus(mainloop=bus_loop)
    bus_name = dbus.service.BusName(ns.bus_name, bus)

    # plugin = OpenConnectPlugin(object_path=NM_DBUS_PATH,
    #                            bus_name=bus_name)
    loop = GLib.MainLoop()
    plugin = Plugin(loop=loop, object_path=NM_DBUS_PATH, bus_name=bus_name)
    plugin.run()


def main():
    ns: Namespace = parser.parse_args()

    # Configure logger on start up.
    global logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON, address='/dev/log')
    logger.addHandler(handler)
    logger.debug('nm-oc: argv: %s', ns)

    try:
        run(ns)
    except Exception:
        logger.exception('nc-oc: throw exception')


if __name__ == '__main__':
    main()
