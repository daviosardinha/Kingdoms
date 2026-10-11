import json
from rich.table import Table
from rich import print
from goad.goadpath import *
from goad.log import Log
from goad.instance import LabInstance


class LabInstances:

    GOAD_NOMAD_NETWORK_SCOPE = '10.4.0.0/16 (segmented)'

    def __init__(self, config):
        self.instances = None
        self._init_instances(config)

    def _init_instances(self, config):
        self.instances = {}
        workspace_path = GoadPath.get_workspace_path()
        for instance in Utils.list_folders(workspace_path):
            instance_info_file = workspace_path + sep + instance + sep + 'instance.json'
            if os.path.isfile(instance_info_file):
                with open(instance_info_file, 'r') as instance_info_openfile:
                    # Reading from json file
                    instance_info = json.load(instance_info_openfile)
                    lab_name = instance_info['lab']
                    provider_name = instance_info['provider']
                    provisioning_method = instance_info['provisioner']
                    ip_range = instance_info['ip_range']
                    extensions = instance_info['extensions']
                    status = instance_info['status']
                    is_default = instance_info['is_default']
                    self.instances[instance] = LabInstance(instance, lab_name, config, provider_name, provisioning_method, ip_range, extensions, status, is_default)

    def nb_instances(self):
        return len(self.instances)

    def add_instance(self, instance):
        self.instances[instance.instance_id] = instance

    def del_instance(self, instance_id):
        del self.instances[instance_id]

    def get_instance(self, instance_id):
        if instance_id in self.instances.keys():
            return self.instances[instance_id]
        else:
            return None

    @staticmethod
    def color_status(status):
        if status == CREATED:
            status = f'[red]{status}[/red]'
        elif status == PROVIDED:
            status = f'[yellow]{status}[/yellow]'
        elif status == READY:
            status = f'[green]{status}[/green]'
        return status

    @staticmethod
    def color_provider(provider):
        if provider == AWS:
            provider = f'[orange1]{provider}[/orange1]'
        elif provider == AZURE:
            provider = f'[deep_sky_blue1]{provider}[/deep_sky_blue1]'
        elif provider == VIRTUALBOX:
            provider = f'[dodger_blue3]{provider}[/dodger_blue3]'
        elif provider == VMWARE:
            provider = f'[cyan3]{provider}[/cyan3]'
        elif provider == VMWARE_ESXI:
            provider = f'[cyan1]{provider}[/cyan1]'
        elif provider == PROXMOX:
            provider = f'[dark_orange3]{provider}[/dark_orange3]'
        return provider

    @staticmethod
    def _is_goad_nomad_segmented(instance):
        return instance.lab_name in ('GOAD', 'NORTH') and instance.provider_name == VMWARE

    def _network_scope(self, instance):
        if self._is_goad_nomad_segmented(instance):
            if instance.lab_name == 'NORTH':
                # The instance owns a segmented /16, not the legacy flat /24.
                # Keep its configured base visible even before install acceptance.
                return instance.ip_range + '.0/16 (segmented)'
            return self.GOAD_NOMAD_NETWORK_SCOPE
        return instance.ip_range + '.0/24'

    def _runtime_mode(self, instance_id, instance):
        if not self._is_goad_nomad_segmented(instance):
            return '-'

        state_file = os.path.join(
            GoadPath.get_instance_provider_path(instance_id),
            '.goad-nomad-mode',
        )
        if not os.path.isfile(state_file):
            return 'unknown'

        with open(state_file, 'r', encoding='utf-8') as handle:
            mode = handle.read().strip()
        return mode if mode else 'unknown'

    def show_instances(self, lab_name='', provider_name='', current_instance_id='', filter_instance_id=''):
        instance_found = False
        table = Table()
        table.add_column('Instance ID')
        table.add_column('Lab')
        table.add_column('Provider')
        table.add_column('Network Scope')
        table.add_column('Status')
        table.add_column('Mode')
        table.add_column('Is Default')
        table.add_column('Extensions')
        for instance_id, instance in self.instances.items():
            # if filter enabled continue only if instance match the filter
            if filter_instance_id != '':
                if instance_id != filter_instance_id:
                    continue

            if lab_name != '' and lab_name != instance.lab_name:
                continue
            if provider_name != '' and provider_name != instance.provider_name:
                continue
            instance_found = True
            table.add_row(f'[red]> [/red][green]{instance_id}[/green]' if instance_id == current_instance_id else instance_id,
                          instance.lab_name,
                          self.color_provider(instance.provider_name),
                          self._network_scope(instance),
                          self.color_status(instance.status),
                          self._runtime_mode(instance_id, instance),
                          'Yes' if instance.is_default else 'No',
                          ", ".join(instance.extensions)
                          )
        if instance_found:
            print(table)
        else:
            Log.warning('No instance found, change your config and use [italic][blue]install[/blue][/italic] to create a lab instance')
