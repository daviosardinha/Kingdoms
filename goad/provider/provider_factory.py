from goad.utils import *
from goad.dependencies import Dependencies
from goad.course_catalog import course_manifest
from goad.provider.course_preview import PreviewCourseProvider



class ProviderFactory:

    @staticmethod
    def get_provider(provider_name, lab_name, config):
        provider = None
        course = course_manifest(lab_name)
        if course is not None:
            # Never reuse the legacy GOAD provider for an unreleased course.
            if (provider_name == VMWARE and Dependencies.vmware_enabled
                    and provider_name in course["providers"]):
                return PreviewCourseProvider(lab_name, provider_name)
            return None
        if provider_name == VIRTUALBOX and Dependencies.virtualbox_enabled:
            from goad.provider.vagrant.virtualbox import VirtualboxProvider
            provider = VirtualboxProvider(lab_name)
        elif provider_name == VMWARE and Dependencies.vmware_enabled:
            from goad.provider.vagrant.vmware_kingdoms_profile import ProfiledGoadKingdomsVmwareProvider
            provider = ProfiledGoadKingdomsVmwareProvider(lab_name)
        elif provider_name == VMWARE_ESXI and Dependencies.vmware_esxi_enabled:
            from goad.provider.vagrant.vmware_esxi import VmwareEsxiProvider
            provider = VmwareEsxiProvider(lab_name)
        elif provider_name == PROXMOX and Dependencies.proxmox_enabled:
            from goad.provider.terraform.proxmox import ProxmoxProvider
            provider = ProxmoxProvider(lab_name, config)
        elif provider_name == AZURE and Dependencies.azure_enabled:
            from goad.provider.terraform.azure import AzureProvider
            provider = AzureProvider(lab_name)
        elif provider_name == AWS and Dependencies.aws_enabled:
            from goad.provider.terraform.aws import AwsProvider
            provider = AwsProvider(lab_name, config)
        elif provider_name == LUDUS and Dependencies.ludus_enabled:
            from goad.provider.ludus.ludus import LudusProvider
            provider = LudusProvider(lab_name, config)
        return provider
