# NORTH configuration — native Kingdoms recipe

This directory now holds Course 1's two-domain configuration and inventories,
derived from the patched Kingdoms repository baseline: KINGSLANDING (parent),
WINTERFELL (child), CASTELBLACK and WS01. ESSOS hosts and forest trust are
excluded, while existing non-ESSOS fixture passwords and scenario attributes
are preserved as course lab data.

`data/inventory` uses `domain_name=NORTH`; the inventory under
`providers/vmware` binds the isolated VMware `10.41.x` addresses.
No live reference workspace, guest or AD state was edited.

**The native VMware provider and instance lifecycle are still release-gated.**
Source presence alone does not make it safe to select `install`.
