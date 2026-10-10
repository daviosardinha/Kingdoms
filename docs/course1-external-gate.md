### External offline artifact acceptance

The existing Python-only profile tests verify the intended four-VM topology.
The next gate checks the actual generated files using the native parsers:

    python3 scripts/course1/check-rendered-artifacts.py --check

This runs only:
- Ruby syntax check on the *rendered* instance Vagrantfile: ruby -c.
- Ansible inventory parsing (--list only, no plays) on the 4-guest
  provisioning inventory, post-Vagrant management inventory, and VMware
  provider inventory.
- Exact hostname/group and post-Vagrant WS01 management identity consistency.

It makes a temporary private directory that is removed automatically. Native
parser output containing fixture credentials is captured and never printed.
If ansible-inventory isn't available on PATH, the command looks for the
existing ~/.goad/.venv/bin/ansible-inventory. No Vagrant/VMware commands are
executed; passing this check does NOT authorize any Course 1 deployment.
