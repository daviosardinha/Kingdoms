"""Fail-closed course provider placeholder for unvalidated native lab recipes."""
from goad.log import Log
from goad.provider.provider import Provider
from goad.utils import PROVISIONING_LOCAL


class PreviewCourseProvider(Provider):
    default_provisioner = PROVISIONING_LOCAL
    allowed_provisioners = [PROVISIONING_LOCAL]
    update_ip_range = False

    def __init__(self, lab_name: str, provider_name: str):
        super().__init__(lab_name)
        self.provider_name = provider_name

    def _blocked(self, action):
        Log.error(
            f'Kingdoms {self.lab_name}/{self.provider_name}: {action} is blocked. '
            'Course profile is visible for discovery, not released for deployment.'
        )
        return False

    def check(self): return self._blocked("check")
    def install(self): return self._blocked("install")
    def destroy(self): return self._blocked("destroy")
    def destroy_non_interactive(self): return self._blocked("destroy")
    def start(self, vm_name=None): return self._blocked("start")
    def stop(self): return self._blocked("stop")
    def start_vm(self, vm_name): return self._blocked("start_vm")
    def stop_vm(self, vm_name): return self._blocked("stop_vm")
    def restart_vm(self, vm_name): return self._blocked("restart_vm")
    def destroy_vm(self, vm_name): return self._blocked("destroy_vm")
    def reset(self): return self._blocked("reset")
    def snapshot(self): return self._blocked("snapshot")
    def status(self): return self._blocked("status")
