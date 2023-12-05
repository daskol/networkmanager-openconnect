# NetworkManager: OpenConnect Plugin

*Simple and flexible NetworkManager support for OpenConnect in Python.*

- [Overview](#overview)
- [Installation](#installation)
- [Configuration](#configuration)
- [Development Issues](#development-Issues)
  - [Traffic Dump](#traffic-dump)
  - [Secrets Agent Availablity](#secrets-agent-availablity)

## Overview

This is a concurrent project aimed in support of [OpenConnect][2] (an
open-source implementation of Cisco's [AnyConnect][1]) within Gnome's
[NetworkManager][4] (or just NM). There are several drawbacks of original
OpenConnect support in NetworkManager.

1. Inability to activate a VPN connection without typing as password. In other
   words, you should type something like the following.

   ```shell
   nmcli connection up YourVPNConn -a
   ```

   The issue is that you should type not only password but a username (sic!) as
   well. Moreover, some corporate networks suggest a choice of role or network
   to connect to. Underlying `openconnect` client allows to specify desired
   form options manually or via comman line options. This implementation
   assumes that all auxiliary options are already enumerated in `nmconnection`
   file, So there is no need in manual typing too.
2. C/C++ gives an excelemnt performance in a cost of laborious development
   efforts. We believe there is no need to write a code in C/C++ here. Python
   is enough in order to execute `openconnect` binary and sleep until a
   connection is deactivated.
3. Original implementation is distributed under toxic GPL.
4. Enormous complexity of DBus and NetworkManager in general. In my perspective
   there are some bizzare things in implementation and internals of DBus.
   Interaction protocol within NetworkManager is [unclear][6] and [vague][7].

## Installation

**NOTE** This implementation conflicts with [original implementation][5].

Since this plugin relies on OpenConnect binary and an architecture and
configuration of original plugin implementation, the first part of installation
process is pretty straightforward: you should just install the packages as
follows.

```shell
apt update && apt install openconnect network-manager-openconnect  # Ubuntu
```

And then install this package.

```shell
pip install git+https://github.com/daskol/networkmanager-openconnect.git
```

The second part is more tedious since we need to update a NetworkManager
configuration a litte bit. We need to edit a service file for a DBus service
which exposes plugin services to NetworkManager. As we finished with the
[configuration file](nm-openconnect-service.name) it should look like the
following.

```ini
# Config file: /usr/lib/NetworkManager/VPN/nm-openconnect-service.name
[VPN Connection]
name=openconnect
service=org.freedesktop.NetworkManager.openconnect
program=/usr/local/bin/networkmanager-openconnect  # Path to executable.
supports-multiple-connections=true
```

Finally, we should reload NetworkManager and activate our VPN connection.

```shell
nmcli connection reload
nmcli connection up YourVPNConn
```

## Configuration

As it was mentioned above, the plugin relies on original implementation. This
is true for configuration as well. Below a snippet of `nmconnection` file shows
the difference with original configuration file. The rest of fields are pretty
the same as in the original configuration (if they are used at all).

```
[vpn]
service-type=org.freedesktop.NetworkManager.openconnect
password-flags=0  # Do not ask agent for secrets.
username=your-username-here  # Username.
form=main:group_list=AccessVPN,main:field=value  # Comma-separated form data.

[vpn-secrets]
password=your-password-here  # Password in plaintext.
```

**NOTE** Some configuration options are not used at all but it is simple enough
to support them.

## Development Issues

### Logging and Configuration

We need to fix logging and read full configuration (support every option of
original `openconnect` binary). Also, logging requires some efforts to make it
behave exactly as the original implementation.

### Traffic Dump

There are plenty amazing tools for monitoring, discovery, introspection, and
communication from scratch.

```shell
busctl --system capture > dbus-traffic.pcap
```

Then one should use `wireshark` to open and analyze the dump.

### Secrets Agent Availablity

There are some issues with access to secrets agent from proccess run with root
priviledges. It requires some research to figure out solution if it is actually
an issue. Also, we need to drop priviledges properly in plugin.

[1]: https://www.cisco.com/c/ru_ru/index.html
[2]: https://github.com/openconnect
[3]: https://www.gnome.org/
[4]: https://networkmanager.dev/
[5]: https://gitlab.gnome.org/GNOME/NetworkManager-openconnect
[6]: https://people.redhat.com/dcbw/NetworkManager/NetworkManager%20DBUS%20API.txt
[7]: https://bugzilla.redhat.com/show_bug.cgi?id=710552
[8]: https://people.freedesktop.org/~lkundrak/nm-docs/gdbus-org.freedesktop.NetworkManager.VPN.Plugin.html
