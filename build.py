#!/usr/bin/python3

import os
from datetime import datetime
import ipaddress
import requests
from requests.exceptions import RequestException, HTTPError

import gfwlist

SOURCES_4 = {
    'ipdeny.com': 'http://www.ipdeny.com/ipblocks/data/aggregated/cn-aggregated.zone',
    '17mon': 'https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt',
}
SOURCES_6 = {
    'gaoyifan': 'https://gaoyifan.github.io/china-operator-ip/china6.txt',
}
SOURCES_46 = {
    'maxmind': 'https://github.com/v2fly/geoip/raw/release/text/cn.txt',
}
OUT_DIR = "dist"

# Stub content to disable GFWList check
GFWLIST_STUB = "var DOMAINS = {};\nvar BLACKPAT = [];\nvar WHITEPAT = [];\n"


def fetch_and_convert(src):
    response = requests.get(src)
    response.raise_for_status()
    template = "var CHINA = [\n{}\n];\n"
    lines = []
    for iprange in response.text.strip().split("\n"):
        if iprange.find(":") != -1:
            break
        ipnet = ipaddress.IPv4Network(iprange)
        netaddr = int(ipnet.network_address)
        netmask = int(ipnet.netmask)
        s = f"  [0x{netaddr:08X}, 0x{netmask:08X}], // {iprange}"
        lines.append(s)
    lines.append("  [0xFFFFFFFF, 0xFFFFFFFF]  // 255.255.255.255/32")  # use broadcast as a placeholder
    return template.format("\n".join(lines))


def fetch_and_convert_ip6(src):
    response = requests.get(src)
    response.raise_for_status()
    text = response.text

    template = "var CHINA6_F = [\n{}\n];\n\n"
    template2 = "var CHINA6_S = [\n{}\n];\n"
    lines = []
    lines2 = []
    lastnum = 0
    count = 0
    begins = False
    ends = False
    lower = 0
    upper = 0
    networkstr_b = ""
    iprangestr_b = ""
    fixlen = len(f"  [0xFFFFFFFF, -1, 0xFFFFFFFF],")

    for iprange in text.strip().split("\n"):
        if iprange.find(":") == -1:
            continue
        ipnet = ipaddress.IPv6Network(iprange)
        prefixlen = ipnet.prefixlen
        fulladdr = str(ipnet.exploded).replace(':', '')
        num1 = int(fulladdr[0:8], 16)
        num2 = int(fulladdr[8:16], 16)
        fullmask = f"{ipnet.netmask:X}"
        mask1 = fullmask[0:8]
        mask2 = fullmask[8:16]

        if lastnum != num1 and begins:
            ends = True

        if ends:
            begins = False
            ends = False
            upper = count - 1
            s2 = networkstr_b
            if upper == lower:
                s2 = iprangestr_b
            s = f"  [0x{lastnum:08X}, {lower}, {upper}],"
            len1 = len(s)
            if len1 < fixlen:
                s = s + " " * (fixlen - len1)
            s = f"{s} // {s2}"
            lines.append(s)

        if prefixlen <= 32:
            if begins:
                raise NameError(f"Invalid list order: \n{iprange}")
            s = f"  [0x{num1:08X}, -1, 0x{mask1}], // {iprange}"
            lines.append(s)
        else:
            if not begins:
                begins = True
                lower = count
                networkstr_b = str(ipnet.exploded)[0:10]
                iprangestr_b = iprange

            s = f"  [0x{num2:08X}, 0x{mask2}], // {count}, {iprange}"
            lines2.append(s)
            count = count + 1
        lastnum = num1

    if begins:
        begins = False
        ends = False
        upper = count - 1
        s2 = networkstr_b
        if upper == lower:
            s2 = iprangestr_b
        s = f"  [0x{lastnum:08X}, {lower}, {upper}],"
        len1 = len(s)
        if len1 < fixlen:
            s = s + " " * (fixlen - len1)
        s = f"{s} // {s2}"
        lines.append(s)
    
    lines.append("  [0xFFFFFFFF, -1, 0xFFFFFFFF]  // ffff:ffff::/32 placeholder")
    lines2.append(f"  [0xFFFFFFFF, 0xFFFFFFFF]  // {count}, placeholder, not in use")

    return template.format("\n".join(lines)) + template2.format("\n".join(lines2))


def write_pac(filename, code, data, data_6, tail):
    with open(os.path.join(OUT_DIR, filename), "w") as f:
        f.write(code)
        f.write(data)
        f.write("\n")
        f.write(data_6)
        f.write("\n")
        f.write(tail)


def main():
    now = datetime.utcnow()
    date = now.strftime("%Y%m%d")
    with open("code.js", "r") as f:
        code = f.read()
    code = code.replace("@@TIME@@", now.isoformat()[:-7])

    gfwlist_part = gfwlist.generate_pac_partial()
    gfwlist_stub = GFWLIST_STUB

    os.makedirs(OUT_DIR, mode=0o755, exist_ok=True)
    for key in SOURCES_4:
        key_6 = list(SOURCES_6)[0]
        print(f"Generating PAC script from source {key}(IPv4) & {key_6}(IPv6)")
        try:
            data = fetch_and_convert(SOURCES_4[key])
            data_6 = fetch_and_convert_ip6(SOURCES_6[key_6])
        except RequestException:
            continue
        except HTTPError:
            continue

        filename = f"pac-IPv4_{key}--IPv6_{key_6}.txt"
        filename_gfwlist = f"pac-gfwlist-IPv4_{key}--IPv6_{key_6}.txt"
        write_pac(filename, code, data, data_6, gfwlist_stub)
        write_pac(filename_gfwlist, code, data, data_6, gfwlist_part)

    for key in SOURCES_46:
        print(f"Generating PAC script from source {key}(IPv4v6)")
        try:
            data = fetch_and_convert(SOURCES_46[key])
            data_6 = fetch_and_convert_ip6(SOURCES_46[key])
        except RequestException:
            continue
        except HTTPError:
            continue

        filename = f"pac-IPv4v6_{key}.txt"
        filename_gfwlist = f"pac-gfwlist-IPv4v6_{key}.txt"
        write_pac(filename, code, data, data_6, gfwlist_stub)
        write_pac(filename_gfwlist, code, data, data_6, gfwlist_part)



if __name__ == '__main__':
    main()
