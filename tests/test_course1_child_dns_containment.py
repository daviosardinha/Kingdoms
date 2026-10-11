"""NORTH AD promotion must not discover the identically named reference forest."""
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "ansible/roles/child_domain/tasks/main.yml"
GUARD = ROOT / "ansible/roles/child_domain/tasks/north_dns_containment.yml"
PROMOTION = ROOT / "ansible/roles/child_domain/tasks/north_promotion.yml"
REFERENCE_DC = "10.4.10.11"
NORTH_PARENT = "10.41.20.10"
NORTH_CHILD = "10.41.10.11"


class NorthChildDnsContainmentTests(unittest.TestCase):
    @staticmethod
    def load(path):
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_north_guard_runs_before_any_child_promotion(self):
        tasks = self.load(ROLE)
        names = [task["name"] for task in tasks]
        guard = next(i for i, x in enumerate(tasks)
                     if x.get("ansible.builtin.include_tasks") == "north_dns_containment.yml")
        legacy = names.index("add child domain to parent domain")
        north = next(i for i, x in enumerate(tasks)
                     if x.get("ansible.builtin.include_tasks") == "north_promotion.yml")
        self.assertLess(guard, legacy)
        self.assertLess(guard, north)
        self.assertEqual(tasks[guard]["when"], "domain_name | default('') == 'NORTH'")
        self.assertEqual(tasks[north]["when"], "domain_name | default('') == 'NORTH'")
        self.assertEqual(tasks[legacy]["when"], "domain_name | default('') != 'NORTH'")

    def test_goa_d_legacy_promotion_is_unchanged_and_gated_out_of_north(self):
        tasks = self.load(ROLE)
        legacy = next(t for t in tasks if t["name"] == "add child domain to parent domain")
        self.assertIn("-SkipPreChecks", legacy["ansible.windows.win_powershell"]["script"])
        self.assertEqual(legacy["when"], "domain_name | default('') != 'NORTH'")
        self.assertEqual(next(t for t in tasks
                              if t["name"].startswith("Reboot legacy GOAD"))["when"][0],
                         "domain_name | default('') != 'NORTH'")

    def test_north_nat_dns_pinned_to_selected_parent_ip(self):
        tasks = self.load(GUARD)
        dns = tasks[0]["ansible.windows.win_dns_client"]
        self.assertEqual(dns["adapter_names"], "{{ nat_adapter }}")
        self.assertEqual(dns["ipv4_addresses"], ["{{ hostvars[dns_domain].ansible_host }}"])
        self.assertEqual(tasks[0]["when"], "two_adapters | bool")
        self.assertNotIn(REFERENCE_DC, GUARD.read_text())

    def test_locator_proof_is_fail_closed_before_promotion(self):
        tasks = self.load(GUARD)
        script = tasks[1]["ansible.windows.win_powershell"]["script"]
        self.assertIn("nltest.exe", script)
        self.assertIn("/force", script)
        self.assertIn("parentAddresses[0] -ne $ParentDns", script)
        self.assertIn("childAddresses[0] -ne $ChildDcIp", script)
        self.assertIn("NORTH_DNS_CONTAINMENT_OK", script)
        self.assertIn("Clear-DnsClientCache", script)
        self.assertIn("natServers[0] -ne $ParentDns", script)
        self.assertIn("ChildDcIp, '127.0.0.1'", script)
        self.assertIn("NORTH DNS containment: unexpected NAT", script)
        self.assertEqual(tasks[1]["changed_when"], False)
        self.assertEqual(tasks[1]["ansible.windows.win_powershell"]["parameters"]["ParentDns"],
                         "{{ hostvars[dns_domain].ansible_host }}")

    def test_north_locator_captures_native_stderr_without_ps_error_records(self):
        # Windows PowerShell 5.1 turns a failing native command's stderr
        # into NativeCommandError with ErrorActionPreference=Stop.
        # Preserve both streams in a bounded Process instead of issuing
        # a pipeline command whose failure occurs before LASTEXITCODE.
        script = self.load(GUARD)[1]["ansible.windows.win_powershell"]["script"]
        self.assertIn("function Invoke-NorthDcLocator", script)
        self.assertIn("System32\\nltest.exe", script)
        self.assertIn("RedirectStandardOutput = $true", script)
        self.assertIn("RedirectStandardError = $true", script)
        self.assertIn("WaitForExit(20000)", script)
        self.assertIn("GetAwaiter().GetResult()", script)
        self.assertIn("if ($parentLookup.ExitCode -ne 0)", script)
        self.assertIn("Invoke-NorthDcLocator -Name $ChildDomain", script)
        self.assertNotIn("& nltest.exe", script)
        self.assertNotIn("$LASTEXITCODE", script)

    def test_only_expected_missing_child_domain_is_accepted(self):
        script = self.load(GUARD)[1]["ansible.windows.win_powershell"]["script"]
        self.assertIn("if ($childStatus -ne 0)", script)
        self.assertNotIn("$childStatus -notin", script)
        self.assertIn("Status\\s*=\\s*1355\\b", script)
        self.assertIn("ERROR_NO_SUCH_DOMAIN", script)
        self.assertIn("$childStatus = 1355", script)
        self.assertIn("DomainRole -ne 2 -or $computer.PartOfDomain", script)
        self.assertIn("child discovery absent but local Windows is not a standalone", script)
        self.assertIn("if ($childStatus -eq 0)", script)
        self.assertIn("childAddresses[0] -ne $ChildDcIp", script)
        self.assertLess(script.index("if ($childStatus -ne 0)"),
                        script.index("$childStatus = 1355"))
        self.assertLess(script.index("if ($childStatus -eq 0)"),
                        script.index("childAddresses[0] -ne $ChildDcIp"))

    def test_never_accept_missing_parent_or_arbitrary_child_failure(self):
        script = self.load(GUARD)[1]["ansible.windows.win_powershell"]["script"]
        self.assertIn("current parent-domain DC Locator failed", script)
        self.assertIn("unexpected child lookup error", script)
        self.assertIn("$childLookup.Stdout", script)
        self.assertIn("$childLookup.Stderr", script)
        self.assertIn("NORTH_DNS_CONTAINMENT_OK parent=$ParentDns child_status=$childStatus", script)
        self.assertNotIn("$ErrorActionPreference = 'Continue'", script)
        self.assertNotIn("-ErrorAction SilentlyContinue", script)

    def test_live_preflight_reuses_exact_guard_without_dns_changes_or_ad_promotion(self):
        probe = ROOT / "ansible/north-child-dns-preflight.yml"
        plays = self.load(probe)
        self.assertEqual(len(plays), 1)
        self.assertEqual(plays[0]["hosts"], "dc02")
        tasks = plays[0]["tasks"]
        self.assertEqual(len(tasks), 5)
        ps = tasks[3]["ansible.windows.win_powershell"]
        self.assertIn("north_dns_containment.yml", ps["script"])
        self.assertIn("from_yaml", ps["script"])
        self.assertEqual(tasks[3]["changed_when"], False)
        self.assertEqual(tasks[3]["register"], "north_dns_proof")
        self.assertEqual(tasks[4]["ansible.builtin.debug"]["var"],
                         "north_dns_proof.output")
        self.assertIn("hostvars['dc01'].ansible_host", str(ps["parameters"]))
        self.assertIn("hostvars['dc02'].ansible_host", str(ps["parameters"]))
        self.assertNotIn("win_dns_client", probe.read_text(encoding="utf-8"))
        self.assertNotIn("Install-ADDSDomain", str(ps))
        self.assertNotIn("win_reboot:", probe.read_text(encoding="utf-8"))
        self.assertNotIn("include_tasks:", probe.read_text(encoding="utf-8"))
        self.assertEqual(plays[0]["gather_facts"], True)

    def test_north_promotion_uses_local_machine_state_not_foreign_directory(self):
        tasks = self.load(PROMOTION)
        promotion = tasks[0]["ansible.windows.win_powershell"]["script"]
        self.assertIn("Get-CimInstance Win32_ComputerSystem", promotion)
        self.assertIn("DomainRole", promotion)
        self.assertIn("Install-ADDSDomain @promotion", promotion)
        self.assertIn("ErrorAction = 'Stop'", promotion)
        self.assertNotIn("SkipPreChecks", promotion.split("$promotion = @{")[1])
        self.assertNotIn("Get-ADDomain -Identity", promotion)
        self.assertLess(promotion.index("Install-ADDSDomain @promotion"),
                        promotion.index("$Ansible.Changed = $true"))

    def test_north_checks_local_dc_after_reboot_before_dns_zone(self):
        tasks = self.load(PROMOTION)
        self.assertEqual(tasks[1]["when"], "north_child_result.changed")
        self.assertEqual(tasks[2]["ansible.windows.win_service"]["name"], "ADWS")
        self.assertEqual(tasks[2]["ansible.windows.win_service"]["state"], "started")
        proof = tasks[3]["ansible.windows.win_powershell"]["script"]
        self.assertIn("DomainRole -ne 5", proof)
        self.assertIn("Get-ADDomain -Current LocalComputer", proof)
        self.assertIn("NORTH_CHILD_DC_PROMOTION_VERIFIED", proof)
        self.assertGreaterEqual(tasks[3]["retries"], 2)

    def test_north_member_guards_precede_server_and_workstation_joins(self):
        plays = self.load(ROOT / "ansible/ad-members.yml")
        for play, legacy in ((plays[1], "member_server"),
                             (plays[2], "commonwkstn")):
            with self.subTest(role=legacy):
                self.assertEqual(play["roles"][0]["role"],
                                 "kingdoms_north_member_dns_guard")
                self.assertEqual(play["roles"][0]["when"],
                                 "domain_name == 'NORTH'")
                self.assertEqual(play["roles"][1]["role"], legacy)

    def test_north_member_nat_dns_and_locator_are_instance_bound(self):
        guard = self.load(
            ROOT / "ansible/roles/kingdoms_north_member_dns_guard/tasks/main.yml"
        )
        self.assertEqual(guard[0]["name"],
                         "Discover NORTH member IPv4 adapters from this Windows host")
        self.assertEqual(guard[1]["ansible.builtin.assert"]["that"][0],
                         "north_member_lab_interfaces | length == 1")
        self.assertIn("north_member_other_interfaces | length <= 1",
                      guard[1]["ansible.builtin.assert"]["that"])
        self.assertIn("two_adapters", guard[2]["ansible.builtin.set_fact"])
        for entry, expected_adapter in zip(guard[3:5], ("domain_adapter", "nat_adapter")):
            with self.subTest(adapter=expected_adapter):
                action = entry["ansible.windows.win_dns_client"]
                self.assertEqual(action["adapter_names"], "{{ " + expected_adapter + " }}")
                self.assertEqual(action["ipv4_addresses"],
                                 ["{{ hostvars[dns_domain].ansible_host }}"])
        self.assertEqual(guard[4]["when"], "two_adapters | bool")
        proof = guard[5]["ansible.windows.win_powershell"]["script"]
        self.assertIn("/dsgetdc:$ExpectedDomain", proof)
        self.assertIn("addresses[0] -ne $ExpectedDns", proof)
        self.assertIn("$checkedInterfaces = @($DomainAdapter)", proof)
        self.assertIn("if ($HasNat)", proof)
        self.assertIn("NORTH_MEMBER_DNS_CONTAINMENT_OK", proof)
        self.assertNotIn(REFERENCE_DC, proof)
        self.assertEqual(guard[5]["changed_when"], False)
        self.assertEqual(guard[5]["ansible.windows.win_powershell"]["parameters"]["HasNat"],
                         "{{ two_adapters | bool }}")

    def test_ws01_single_homed_and_srv02_dual_homed_are_resolved_per_host(self):
        from jinja2 import StrictUndefined
        from jinja2.nativetypes import NativeEnvironment
        tasks = self.load(
            ROOT / "ansible/roles/kingdoms_north_member_dns_guard/tasks/main.yml"
        )
        env = NativeEnvironment(undefined=StrictUndefined)
        lab = {"connection_name": "Ethernet1",
               "ipv4": {"address": "10.41.10.31"}}
        nat = {"connection_name": "Ethernet0",
               "default_gateway": "192.168.213.2",
               "ipv4": {"address": "192.168.213.239"}}
        for interfaces, expected_nat, valid in (
            ([lab], False, True),
            ([lab, nat], True, True),
            ([lab, nat, {**nat, "connection_name": "Ethernet2"}], True, False),
            ([lab, {"connection_name": "Ethernet2"}], False, False),
            ([nat], False, False),
            ([], False, False),
        ):
            with self.subTest(interfaces=interfaces):
                context = {"ansible_interfaces": interfaces,
                           "ansible_host": "10.41.10.31"}
                binding = tasks[0]["ansible.builtin.set_fact"]
                lab_matches = env.from_string(
                    binding["north_member_lab_interfaces"]
                ).render(**context)
                other_matches = env.from_string(
                    binding["north_member_other_interfaces"]
                ).render(**context)
                context.update(north_member_lab_interfaces=lab_matches,
                               north_member_other_interfaces=other_matches)
                topology_ok = (
                    len(lab_matches) == 1 and len(other_matches) <= 1 and
                    len(interfaces) == len(lab_matches) + len(other_matches) and
                    bool(lab_matches[0].get("connection_name")) and
                    (len(other_matches) == 0 or
                     (bool(other_matches[0].get("connection_name")) and
                      other_matches[0].get("default_gateway") is not None))
                )
                self.assertEqual(topology_ok, valid)
                if not valid:
                    continue
                resolved = tasks[2]["ansible.builtin.set_fact"]
                self.assertEqual(
                    env.from_string(resolved["domain_adapter"]).render(**context),
                    "Ethernet1"
                )
                self.assertEqual(
                    env.from_string(resolved["nat_adapter"]).render(**context),
                    "Ethernet0" if expected_nat else ""
                )
                self.assertIs(
                    env.from_string(resolved["two_adapters"]).render(**context),
                    expected_nat
                )

    def test_member_guard_rejects_stale_dc01_nic_facts_and_unexpected_nat(self):
        source = (ROOT / "ansible/roles/kingdoms_north_member_dns_guard/tasks/main.yml").read_text()
        self.assertIn("ansible_interfaces | selectattr", source)
        self.assertIn("ansible_host", source)
        self.assertIn("north_member_other_interfaces | length <= 1", source)
        self.assertIn("ansible_interfaces | length == (north_member_lab_interfaces | length + north_member_other_interfaces | length)", source)
        self.assertIn("north_member_other_interfaces[0].default_gateway", source)
        self.assertIn("NORTH member network evidence is ambiguous", source)
        self.assertIn("HasNat: \"{{ two_adapters | bool }}\"", source)
        self.assertNotIn('adapter_names: "Ethernet0"', source)
        self.assertNotIn('DomainAdapter: "Ethernet1"', source)

    def test_member_live_preflight_reuses_actual_role_dclocator_without_mutation(self):
        playbook = ROOT / "ansible/north-members-nic-preflight.yml"
        plays = self.load(playbook)
        self.assertEqual(len(plays), 1)
        self.assertEqual(plays[0]["hosts"], "srv02:ws01")
        self.assertTrue(plays[0]["gather_facts"])
        tasks = plays[0]["tasks"]
        guard = self.load(
            ROOT / "ansible/roles/kingdoms_north_member_dns_guard/tasks/main.yml"
        )
        self.assertEqual(len(tasks), 7)
        self.assertEqual(tasks[1]["ansible.builtin.set_fact"],
                         guard[0]["ansible.builtin.set_fact"])
        self.assertEqual(tasks[2]["ansible.builtin.assert"]["that"],
                         guard[1]["ansible.builtin.assert"]["that"])
        self.assertEqual(tasks[3]["ansible.builtin.set_fact"],
                         guard[2]["ansible.builtin.set_fact"])
        proof = tasks[5]["ansible.windows.win_powershell"]
        self.assertIn("kingdoms_north_member_dns_guard/tasks/main.yml", proof["script"])
        self.assertIn("from_yaml)[5]", proof["script"])
        self.assertEqual(proof["parameters"]["ExpectedDns"],
                         "{{ hostvars['dc02'].ansible_host }}")
        self.assertEqual(proof["parameters"]["HasNat"], "{{ two_adapters | bool }}")
        self.assertEqual(tasks[5]["changed_when"], False)
        self.assertEqual(tasks[6]["ansible.builtin.debug"]["var"],
                         "north_member_dns_proof.output")
        text = playbook.read_text(encoding="utf-8")
        self.assertNotIn("win_dns_client:", text)
        self.assertNotIn("win_domain_membership:", text)
        self.assertNotIn("microsoft.ad.membership:", text)
        self.assertNotIn("win_reboot:", text)
        self.assertNotIn("include_role:", text)

    def test_ws01_missing_nat_skips_nat_dns_but_not_dc_locator(self):
        guard = self.load(
            ROOT / "ansible/roles/kingdoms_north_member_dns_guard/tasks/main.yml"
        )
        self.assertEqual(guard[4]["when"], "two_adapters | bool")
        proof = guard[5]["ansible.windows.win_powershell"]["script"]
        self.assertIn("$checkedInterfaces = @($DomainAdapter)", proof)
        self.assertIn("if ($HasNat)", proof)
        self.assertIn("$checkedInterfaces += $NatAdapter", proof)
        self.assertIn("nltest.exe", proof)
        self.assertIn("addresses[0] -ne $ExpectedDns", proof)
        self.assertNotIn("10.4.10.11", proof)

    def test_cross_instance_reference_and_north_addresses_remain_distinct(self):
        import json
        lab = json.loads((ROOT / "ad/NORTH/data/config.json").read_text())["lab"]
        inventory = (ROOT / "ad/NORTH/providers/vmware/inventory").read_text()
        self.assertEqual(lab["hosts"]["dc02"]["domain"], "north.sevenkingdoms.local")
        self.assertIn(NORTH_PARENT, inventory)
        self.assertIn(NORTH_CHILD, inventory)
        self.assertNotIn(REFERENCE_DC, inventory)


if __name__ == "__main__":
    unittest.main()
