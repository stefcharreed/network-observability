#!/usr/bin/env bash
# Downloads the MIB files generator.yml needs to build a custom snmp.yml
# (if_mib, unchanged from the exporter's default, plus cisco_cpu). Re-run
# this any time mibs/ is missing or generator.yml gains a new module that
# needs a MIB not already here.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p mibs
cd mibs

CISCO_BASE="https://raw.githubusercontent.com/cisco/cisco-mibs/f55dc443daff58dfc86a764047ded2248bb94e12/v2"
for f in CISCO-SMI CISCO-TC CISCO-PROCESS-MIB ENTITY-MIB; do
  curl -sf -o "$f.my" "$CISCO_BASE/$f.my"
  echo "fetched $f.my"
done

NET_SNMP_BASE="https://raw.githubusercontent.com/net-snmp/net-snmp/v5.9/mibs"
for f in SNMPv2-SMI SNMPv2-TC SNMPv2-CONF SNMPv2-MIB SNMP-FRAMEWORK-MIB HCNUM-TC IF-MIB; do
  curl -sf -o "$f.my" "$NET_SNMP_BASE/$f.txt"
  echo "fetched $f.my"
done

curl -sf -o "IANA-IFTYPE-MIB.my" "https://www.iana.org/assignments/ianaiftype-mib/ianaiftype-mib"
echo "fetched IANA-IFTYPE-MIB.my"

echo "Done. Next: from snmp_exporter/generator/, run"
echo "  docker run --rm -v \"\$(pwd)\":/opt prom/snmp-generator:v0.30.1 generate"
echo "then move the result up: mv snmp.yml ../snmp.yml"
