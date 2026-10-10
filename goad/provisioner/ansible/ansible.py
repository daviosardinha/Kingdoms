import os.path
import time
import yaml
from goad.utils import *
from goad.log import Log
from goad.provisioner.provisioner import Provisioner
from goad.goadpath import GoadPath


class Ansible(Provisioner):

    @staticmethod
    def _format_install_elapsed(seconds):
        total = max(0, int(round(seconds)))
        minutes, secs = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f'{hours}h {minutes:02d}m {secs:02d}s'
        return f'{minutes}m {secs:02d}s'

    def _kingdoms_install_profile(self):
        # The install timing profile is also the in-process lifecycle marker
        # for a fresh, pre-AD provider -> Ansible handoff. NORTH must enter
        # this path rather than the installed-lab AD-aware mode controller.
        if self.lab_name not in ('GOAD', 'NORTH'):
            return None
        profile = getattr(self.provider, '_kingdoms_install_profile', None)
        if not isinstance(profile, dict) or profile.get('status') != 'awaiting_ansible':
            return None
        if self.lab_name == 'NORTH':
            from pathlib import Path
            from goad.course_catalog import north_first_install_pilot_authorized

            # An old timing JSON or a manually invoked playbook cannot
            # authorize a pre-AD bootstrap. This must be THIS in-process
            # provider's successful, instance-bound first-install attempt,
            # with the exact pilot opt-in still active.
            if (not north_first_install_pilot_authorized()
                    or profile.get('provider_success') is not True
                    or profile.get('instance_id') != Path(self.instance_path).name
                    or not self.provider.is_goad_nomad_segmented()
                    or not self.provider._north_runtime_allowed()):
                return None
        return profile

    def _record_kingdoms_ansible_timing(self, phases, label, started, outcome, kind):
        elapsed = time.monotonic() - started
        phases.append({'label': label, 'seconds': elapsed, 'outcome': outcome, 'kind': kind})
        Log.info(
            f'GOAD Kingdoms install timing: {label} = '
            f'{self._format_install_elapsed(elapsed)} ({outcome})'
        )
        self.provider._save_install_profile()
        return elapsed

    def _profile_ansible_call(self, profile, label, func, *args, kind='phase', **kwargs):
        if profile is None:
            return func(*args, **kwargs)
        started = time.monotonic()
        outcome = 'error'
        try:
            result = func(*args, **kwargs)
            outcome = 'failed' if result is False else 'succeeded'
            return result
        except KeyboardInterrupt:
            outcome = 'interrupted'
            raise
        finally:
            self._record_kingdoms_ansible_timing(
                profile['ansible_phases'], label, started, outcome, kind,
            )

    def _run_playbook_attempt(self, playbook, attempt, func, *args):
        # Active only inside this full installation. Standalone playbooks and
        # subsequent console commands cannot append to a completed attempt.
        profile = getattr(self, '_active_install_profile', None)
        return self._profile_ansible_call(
            profile, f'Playbook attempt {playbook} #{attempt}', func, *args,
            kind='playbook_attempt',
        )

    def _emit_kingdoms_install_timing(self, profile, ansible_phases, ansible_started, success):
        if profile is None:
            return

        ansible_elapsed = profile['ansible_elapsed']
        provider_elapsed = profile.get('provider_elapsed')
        overall_started = profile.get('started')
        overall_elapsed = (
            profile['finished'] - overall_started
            if isinstance(overall_started, (int, float))
            else None
        )

        Log.info('=== KINGDOMS INSTALL TIMING SUMMARY ===')
        Log.info('Attempt: ' + profile['attempt_id'])
        Log.info('This invocation only. Nested phase timings must not be added to totals.')
        for phase in profile.get('phases', []):
            Log.info(
                f"  provider | {phase['label']:<52} "
                f"{self._format_install_elapsed(phase['seconds'])}"
            )
        if isinstance(provider_elapsed, (int, float)):
            Log.info(
                '  provider | TOTAL'.ljust(65)
                + self._format_install_elapsed(provider_elapsed)
            )

        for phase in ansible_phases:
            if phase.get('kind') == 'playbook_attempt':
                continue  # Attempts are included in their parent playbook row.
            Log.info(
                f"  ansible  | {phase['label']:<52} "
                f"{self._format_install_elapsed(phase['seconds'])}"
            )
        Log.info(
            '  ansible  | TOTAL'.ljust(65)
            + self._format_install_elapsed(ansible_elapsed)
        )
        if isinstance(overall_elapsed, (int, float)):
            Log.info(
                '  measured | END-TO-END'.ljust(65)
                + self._format_install_elapsed(overall_elapsed)
            )

        message = 'GOAD Kingdoms installation timing capture complete'
        if success:
            Log.success(message)
        else:
            Log.warning(message + ' (installation incomplete)')

    def _get_lab_inventory(self, lab_name, provider_name):
        inventory = []
        # Lab inventory
        lab_inventory = GoadPath.get_lab_inventory_file(lab_name)
        if os.path.isfile(lab_inventory):
            inventory.append(lab_inventory)
            Log.success(f'Lab inventory : {lab_inventory} file found')
        # lab instance inventory
        instance_inventory = self.instance_path + os.path.sep + 'inventory'
        if os.path.isfile(instance_inventory):
            inventory.append(instance_inventory)
            Log.success(f'Provider inventory : {instance_inventory} file found')
        return inventory

    def _get_global_inventory(self):
        # Global inventory
        global_inventory = GoadPath.get_global_inventory_path()
        if os.path.isfile(global_inventory):
            Log.success(f'Global inventory : {global_inventory} file found')
            return global_inventory
        return None

    def _prepare_provider_provisioning(self):
        prepare = getattr(self.provider, 'prepare_provisioning', None)
        if callable(prepare) and not prepare():
            Log.error('Provider failed to prepare the provisioning network state')
            return False
        return True

    def _finalize_provider_provisioning(self):
        finalize = getattr(self.provider, 'finalize_install', None)
        if callable(finalize) and not finalize():
            Log.error('Provider failed to finalize the installed lab state')
            return False
        return True

    def get_inventory(self, lab_name, provider_name):
        Log.info('Loading inventory')
        inventory = self._get_lab_inventory(lab_name, provider_name)
        global_inventory = self._get_global_inventory()
        if global_inventory is not None:
            inventory.append(global_inventory)
        return inventory

    def get_playbook_list(self, lab_name):
        Log.info('Loading playbook list')
        playbook_organisation_file = GoadPath.get_playbooks_lab_config()
        playbook_list = []
        with open(playbook_organisation_file, 'r') as playbooks:
            data_loaded = yaml.safe_load(playbooks)
        if lab_name in data_loaded:
            playbook_datas = data_loaded[lab_name]
        else:
            playbook_datas = data_loaded['default']

        # validate playbooks
        for playbook in playbook_datas:
            playbook_path = GoadPath.get_provisioner_path() + playbook
            if not os.path.isfile(playbook_path):
                Log.error(f'{playbook} not valid, file {playbook_path} not found')
            else:
                playbook_list.append(playbook)
                Log.success(f'{playbook} file found')
        return playbook_list

    def run(self, playbook=None):
        profile = self._kingdoms_install_profile() if playbook is None else None
        if profile is None:
            # A failed first-install handshake must NEVER fall back to the
            # installed/AD-aware provisioning controller while the forest-root
            # DC may still be unpromoted. Refuse promptly and preserve the
            # instance instead of waiting for DC Locator for 300 seconds.
            candidate = getattr(self.provider, '_kingdoms_install_profile', None)
            if (self.lab_name == 'NORTH' and playbook is None
                    and isinstance(candidate, dict)
                    and candidate.get('status') == 'awaiting_ansible'):
                Log.error(
                    'Kingdoms NORTH: first-install Ansible handoff rejected '
                    '(pilot authorization, provider result, or instance binding); '
                    'refusing AD-aware fallback before domain promotion'
                )
                return False
            return self._run(playbook)
        ansible_started = time.monotonic()
        profile['status'] = 'ansible_running'
        previous = getattr(self, '_active_install_profile', None)
        self._active_install_profile = profile
        self.provider._save_install_profile()
        result = False
        outcome = 'failed'
        try:
            result = self._run(playbook, profile)
            return result
        except KeyboardInterrupt:
            outcome = 'interrupted'
            raise
        finally:
            self._active_install_profile = previous
            if self.lab_name == 'NORTH' and not result:
                # Ansible can fail before DC01 has been promoted. Running the
                # normal mode controller here repeats the 300s AD deadlock.
                # Only close the current, authorized NORTH provider's host
                # route and router forwarding. Keep the instance NOT READY.
                abort = getattr(self.provider, 'abort_north_failed_provisioning', None)
                if callable(abort):
                    try:
                        if not abort():
                            Log.error(
                                'Kingdoms NORTH: failed Ansible cleanup unverified; '
                                'inspect networking before retry'
                            )
                    except Exception as exc:
                        Log.error(
                            f'Kingdoms NORTH: failed Ansible cleanup raised: {exc}'
                        )
                else:
                    Log.error(
                        'Kingdoms NORTH: no failure cleanup implementation; '
                        'operator must inspect temporary routing'
                    )
            profile['finished'] = time.monotonic()
            profile['ansible_elapsed'] = profile['finished'] - ansible_started
            profile['status'] = 'completed' if result else outcome
            if self.provider._save_install_profile():
                Log.info('GOAD Kingdoms timing saved: ' + profile['_path'])
            self._emit_kingdoms_install_timing(
                profile, profile['ansible_phases'], ansible_started, bool(result),
            )

    def _run(self, playbook=None, profile=None):
        full_lab_run = playbook is None

        # GOAD_NOMAD providers may need to rebuild an out-of-band management
        # plane before a complete Ansible run. For normal providers the hook is
        # absent and upstream behaviour is unchanged.
        if full_lab_run:
            prepared = self._profile_ansible_call(
                profile, 'Provisioning management-plane preparation',
                self._prepare_provider_provisioning,
            )
            if not prepared:
                return False

        inventory = self.get_inventory(self.lab_name, self.provider_name)
        provision_result = False
        if playbook is None:
            playbooks = self.get_playbook_list(self.lab_name)
            for playbook in playbooks:
                provision_result = self._profile_ansible_call(
                    profile, f'Playbook {playbook}', self.run_playbook, playbook, inventory,
                )
                if not provision_result:
                    Log.error(f'Something wrong during the provisioning task : {playbook}')
                    return False
        else:
            provision_result = self.run_playbook(playbook, inventory)

        # A successful full GOAD_NOMAD installation must never leave the
        # provisioning bypasses enabled. Provider-specific finalization moves
        # the lab into its normal exercise/training state before READY is set by
        # the controller.
        if full_lab_run and provision_result:
            return self._profile_ansible_call(
                profile, 'Final exercise-mode transition',
                self._finalize_provider_provisioning,
            )

        return provision_result

    def run_extension(self, extension, current_instance_extensions_name, install=True):
        # Extension installation can call provider.install() first, which opens
        # the GOAD_NOMAD management plane. Keep the Ansible phase inside the
        # same reversible lifecycle and always close the provisioning bypasses
        # after a successful extension deployment.
        if not self._prepare_provider_provisioning():
            return False

        inventory = self._get_lab_inventory(self.lab_name, self.provider_name)

        # add the inventory of other enabled extensions
        for instances_extension_name in current_instance_extensions_name:
            if instances_extension_name != extension.name:
                other_extension_inventory = self.instance_path + os.path.sep + instances_extension_name + '_inventory'
                if other_extension_inventory is not None:
                    inventory.append(other_extension_inventory)

        # add the current extension inventory at the end
        extension_inventory = self.instance_path + os.path.sep + extension.name + '_inventory'
        if extension_inventory is not None:
            inventory.append(extension_inventory)

        global_inventory = self._get_global_inventory()
        if global_inventory is not None:
            inventory.append(global_inventory)

        playbook = extension.get_playbook(install)
        extension_ansible_path = extension.get_ansible_path()

        provision_result = self.run_playbook(playbook, inventory, playbook_path=extension_ansible_path)
        if not provision_result:
            Log.error(f'Something wrong during the provisioning task : {playbook}')
            return False
        return self._finalize_provider_provisioning()

    def run_from(self, task):
        if task == '' or task is None:
            Log.error('Missing playbook to start from')
            playbooks = self.get_playbook_list(self.lab_name)
            Log.info('Playbook list :')
            for playbook in playbooks:
                Log.info(f' - {playbook}')
            return False

        if not self._prepare_provider_provisioning():
            return False

        inventory = self.get_inventory(self.lab_name, self.provider_name)
        playbooks = self.get_playbook_list(self.lab_name)

        skip = True
        for playbook in playbooks:
            if playbook == task:
                skip = False
            if skip:
                Log.info(f'skip {playbook}')
            else:
                provision_result = self.run_playbook(playbook, inventory)
                if not provision_result:
                    Log.error(f'Something wrong during the provisioning task : {playbook}')
                    return False
        return self._finalize_provider_provisioning()

    def run_playbook(self, playbook, inventories, tries=3, timeout=30, playbook_path=None):
        # abstract
        pass

    def get_disable_vagrant_inventory(self):
        Log.info('Loading inventory')
        inventory = []
        lab_inventory = self.instance_path + os.path.sep + 'inventory_disable_vagrant'
        if os.path.isfile(lab_inventory):
            inventory.append(lab_inventory)
            Log.success(f'Lab inventory disable_vagrant : {lab_inventory} file found')
        global_inventory = self._get_global_inventory()
        if global_inventory is not None:
            inventory.append(global_inventory)
        return inventory

    def run_disable_vagrant(self, disable_vagrant=True):
        inventory = self.get_disable_vagrant_inventory()
        if disable_vagrant:
            playbook = 'disable_vagrant.yml'
        else:
            playbook = 'enable_vagrant.yml'
        provision_result = self.run_playbook(playbook, inventory)
        if not provision_result:
            Log.error(f'Something wrong during the provisioning task : {playbook}')
            return False
        return provision_result
