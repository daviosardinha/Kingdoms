"""Public lab aliases used at the console boundary only.

Keep legacy GOAD names in stored instances, Vagrant paths, provider
selection and network/lifecycle contracts. This module must remain
side-effect free so resolving a name never starts a VM or mutates state.
"""


def canonical_lab_name(name):
    """Translate a public lab selection into its existing internal identity."""
    return 'GOAD' if name == 'KINGDOMS' else name


def public_lab_name(name):
    """Display the full Kingdoms lab without changing its internal identity."""
    return 'KINGDOMS' if name == 'GOAD' else name
