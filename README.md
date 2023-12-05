# NetworkManager: Simple OpenConnect Plugin

*Simple and flexible NetworkManager support for OpenConnect in Python.*

## Overview

1. drawbacks

## Development Issues

### Traffic

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

[1]: https://bugzilla.redhat.com/show_bug.cgi?id=710552
