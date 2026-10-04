# Installed KINGDOMS offline startup

The KINGDOMS console starts an already managed router through local `vmrun`
power control and checks SSH on `10.4.99.1:22`. It does not wait for the router's
NAT address. Mode switching and router runtime checks use the same management
SSH helper. The host must own `10.4.99.254/24`, never the router's `.1` address.

Normal console `start` also powers on all six installed Windows guests through
local `vmrun`, without invoking `vagrant up`, NAT address discovery, forwarded
WinRM ports, or automatic provisioning/recovery. It opens the existing temporary
router policy/routes before checking each inventory address directly on HTTPS
WinRM port 5986. Power-on is bounded to 60 seconds per guest; readiness uses up to
300 seconds per endpoint within a shared 600-second budget, with individual
network-operation timeouts. The original exercise isolation is restored even if
readiness fails or the operator interrupts startup. Already running guests are
not powered on again. Missing VM files or an unknown recorded mode cause `start`
to fail instead of silently creating or repairing machines.

`start_vm NAME` uses the same preflight, sudo keepalive and mode restoration as
`start`. It starts only the selected Windows guest plus the router dependency;
`start_vm GOAD-ROUTER` starts only the router. Other Windows guests are not
started. All seven VM files must already exist in the installed instance.

`stop` requests local VMware Tools soft shutdown of member workstations/servers,
then domain controllers, then the router. It never runs the initial Vagrant halt
or waits for a NAT communicator. The existing bounded hard-power fallback is
retained for a guest that remains running after soft shutdown. A soft-command
timeout still allows the guest time to finish; unknown VMware state blocks hard
fallback. If any Windows guest remains running, the router stays available and
the command reports failure.

`stop_vm NAME` uses the same local shutdown mechanism for that guest only. It
rejects stopping the router while Windows guests are running. Unknown names are
rejected before state changes; already-stopped guests are no-ops. A previously
unreaped Vagrant controller blocks local shutdown to avoid racing its actions.

A recorded `exercise` or `provisioning` mode selects this installed path.
Missing router state, failed SSH, or failed nftables readiness stops startup
without silently recreating or reprovisioning the router. Fresh instances with
no recorded mode still use Vagrant provisioning and need locally available
boxes plus package access for installation.

The installed router prefers a stable Kingdoms management key at
`~/.config/kingdoms/router-management-ed25519`. During migration it can still
try the instance's Vagrant private key and Vagrant's initial insecure key, but
those identities are treated only as bootstrap/recovery paths. This avoids
making the installed management plane depend on Vagrant's generated machine
key remaining synchronized forever. The first management SSH host key remains
pinned in the instance's `management_known_hosts`; a changed host key is
rejected.

The host-address timer now schedules from timer activation and repeats 15
seconds after the helper finishes. Setup activates the service synchronously.
Validation rejects an elapsed timer with no next run; an executing oneshot is
accepted while it is activating. This handles setup long after boot and avoids
overlap when interface recreation takes longer than the repeat interval.

## Apply to an existing lab

Stop all VMware guests before running network setup (the setup script enforces
this). From the updated repository:

```bash
sudo bash scripts/setup-vmware-networks.sh
bash scripts/check-vmware-networks.sh
./goad.sh
```

Select the existing instance and use `start`. Generated instance Vagrantfiles
gain disabled box-update checks automatically during the compatibility step.
Do not recreate the workspace. Direct `vagrant up GOAD-ROUTER` still uses the
provider's native NAT discovery; use the KINGDOMS console for installed startup.

## Host acceptance check

With all guests stopped, disable Wi-Fi and start the existing instance. Confirm
the log reports management SSH ready at `10.4.99.1`, the normal Windows readiness
checks pass, and the original exercise mode is restored. Verify the timer is
waiting with a next trigger and produces repeated successful service runs.
Repeat after restarting the timer long after host boot.

After updating and restarting the console, test the remaining lifecycle commands
with Wi-Fi disabled, beginning with the full range running. Execute each command
after the previous one returns, and stop testing if it reports failure:

```text
stop_vm GOAD-WS01
start_vm GOAD-WS01
stop
status
start_vm GOAD-ROUTER
status
start_vm GOAD-DC03
status
start
status
```

After `stop`, all seven must be stopped. The first single start should leave
only the router running; the next should leave only the router and DC03 running.
Final `start` should restore all seven and exercise isolation. No normal
lifecycle operation above should print `vagrant up` or `vagrant halt`.
`status` still uses read-only `vagrant status`. A healthy shutdown should use
soft shutdown only; report any hard fallback for review before merging.

The repository regression tests mock VMware/systemd; they do not establish that
the full lab starts offline on Workstation. Explicit installation/repair still
uses its existing Vagrant path. The observed association between Wi-Fi state and
router NAT carrier does not establish the underlying VMware cause.
