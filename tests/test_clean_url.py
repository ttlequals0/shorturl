#!/usr/bin/env python3
"""Tests for clean_url. Run: python3 tests/test_clean_url.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "shortener"))

from clean_url import clean_url

FAILURES = []


def check(name, got, want):
  if got != want:
    FAILURES.append("%s\n  got:  %r\n  want: %r" % (name, got, want))


def url(name, given, want_url, want_removed):
  check(name, clean_url(given), (want_url, want_removed))


url("strips a lone utm param and the whole query string with it",
    "https://example.com/page?utm_source=news",
    "https://example.com/page", ["utm_source"])

url("keeps real params and drops only the trackers",
    "https://example.com/p?id=42&utm_source=news&page=2&fbclid=abc",
    "https://example.com/p?id=42&page=2", ["utm_source", "fbclid"])

url("leaves a url with no query untouched",
    "https://example.com/page", "https://example.com/page", [])

url("leaves a url with only real params untouched",
    "https://example.com/p?id=42&page=2", "https://example.com/p?id=42&page=2", [])

url("preserves the original percent-encoding of surviving params",
    "https://example.com/s?q=a%20b&utm_source=news",
    "https://example.com/s?q=a%20b", ["utm_source"])

url("keeps the fragment when the query is emptied",
    "https://example.com/doc?utm_campaign=x#section-3",
    "https://example.com/doc#section-3", ["utm_campaign"])

url("does not touch tracking params inside the fragment",
    "https://example.com/doc#utm_source=news",
    "https://example.com/doc#utm_source=news", [])

url("matches param names case-insensitively",
    "https://example.com/p?UTM_Source=news&linkCode=ll1",
    "https://example.com/p", ["UTM_Source", "linkCode"])

url("keeps a param with an empty value",
    "https://example.com/p?debug=&utm_medium=email",
    "https://example.com/p?debug=", ["utm_medium"])

url("keeps a valueless param that is not a tracker",
    "https://example.com/p?raw&gclid=xyz",
    "https://example.com/p?raw", ["gclid"])

url("strips a valueless tracking param",
    "https://example.com/p?id=1&fbclid",
    "https://example.com/p?id=1", ["fbclid"])

url("strips every occurrence of a repeated tracking param",
    "https://example.com/p?tag=a&id=1&tag=b",
    "https://example.com/p?id=1", ["tag", "tag"])

url("preserves the order of the params it keeps",
    "https://example.com/p?z=1&utm_term=x&a=2&m=3",
    "https://example.com/p?z=1&a=2&m=3", ["utm_term"])

url("strips the amazon affiliate set",
    "https://www.amazon.com/dp/B01?tag=aff-20&linkCode=ogi&th=1&psc=1&ascsubtag=xyz",
    "https://www.amazon.com/dp/B01?th=1&psc=1", ["tag", "linkCode", "ascsubtag"])

url("leaves a non-http scheme alone",
    "mailto:someone@example.com?subject=hi&utm_source=news",
    "mailto:someone@example.com?subject=hi&utm_source=news", [])

url("preserves port, userinfo and a trailing slash",
    "https://user@example.com:8443/a/?utm_source=news",
    "https://user@example.com:8443/a/", ["utm_source"])

url("returns an empty string unchanged", "", "", [])

url("leaves a bare tracking-looking path segment alone",
    "https://example.com/utm_source/page",
    "https://example.com/utm_source/page", [])

url("strips hubspot and mailchimp email trackers",
    "https://example.com/a?_hsenc=p2A&_hsmi=123&mc_cid=abc&mc_eid=def&keep=1",
    "https://example.com/a?keep=1", ["_hsenc", "_hsmi", "mc_cid", "mc_eid"])

GRANOLA = (
  "https://www.granola.ai/?pid=metaweb_int"
  "&c=CTX_US_PRO_Advantage_Web_AccountCreatedDesktop7DC_Scaling_CLS001"
  "&af_siteid=fb&af_c_id=120250414100750509"
  "&af_adset=US_BAU_ASC_All_Mix_WINNERS_7DC_CLS001"
  "&af_adset_id=120250428591920509"
  "&af_ad=14-09-2026_C260_g12_v2_s-siha_t-static_g-na_ta-dailydoers_ai-regular_vp-bepresent_f-tof"
  "&af_ad_id=120250451355840509&utm_id=120250414100750509"
)

check("strips an appsflyer campaign url down to the bare origin",
      clean_url(GRANOLA)[0], "https://www.granola.ai/")

url("strips utm_id, which the reference list omits",
    "https://example.com/p?id=1&utm_id=12345",
    "https://example.com/p?id=1", ["utm_id"])

url("strips the newer ga4 utm params by prefix",
    "https://example.com/p?utm_source_platform=x&utm_creative_format=y&utm_marketing_tactic=z&k=1",
    "https://example.com/p?k=1",
    ["utm_source_platform", "utm_creative_format", "utm_marketing_tactic"])

url("strips the appsflyer af_ family by prefix",
    "https://example.com/p?af_siteid=fb&af_ad_id=99&keep=1",
    "https://example.com/p?keep=1", ["af_siteid", "af_ad_id"])

url("strips pid and c when an af_ param is present alongside them",
    "https://example.com/p?pid=meta&c=camp1&af_siteid=fb&sku=9",
    "https://example.com/p?sku=9", ["pid", "c", "af_siteid"])

url("keeps pid when no af_ param is present, because it is usually a product id",
    "https://shop.example.com/item?pid=88512&color=red",
    "https://shop.example.com/item?pid=88512&color=red", [])

url("keeps a lone c param when no af_ param is present",
    "https://example.com/p?c=3&page=2", "https://example.com/p?c=3&page=2", [])

url("does not let the af_ prefix swallow params that merely start with af",
    "https://example.com/p?after=2&affirm=yes",
    "https://example.com/p?after=2&affirm=yes", [])

url("does not let the utm_ prefix swallow a param named utm",
    "https://example.com/p?utm=1", "https://example.com/p?utm=1", [])

url("strips the twitter, reddit, pinterest and impact click ids",
    "https://example.com/p?twclid=a&rdt_cid=b&epik=c&irclickid=d&wbraid=e&keep=1",
    "https://example.com/p?keep=1",
    ["twclid", "rdt_cid", "epik", "irclickid", "wbraid"])

url("strips matomo and piwik prefixes",
    "https://example.com/p?mtm_campaign=a&pk_campaign=b&id=7",
    "https://example.com/p?id=7", ["mtm_campaign", "pk_campaign"])

url("strips the google cross-domain linker and gclsrc",
    "https://example.com/p?_gl=1*abc&gclsrc=aw.ds&q=x",
    "https://example.com/p?q=x", ["_gl", "gclsrc"])

VIKTOR = ("https://viktor.com/?fb_cid=120251984762390114"
          "&fb_asid=120252065294800114&fb_aid=120252065328550114"
          "&placement=Facebook_Desktop_Feed")

check("strips a meta ads url down to the bare origin",
      clean_url(VIKTOR)[0], "https://viktor.com/")

url("strips the meta fb_ family by prefix",
    "https://example.com/p?fb_cid=1&fb_asid=2&fb_aid=3&keep=9",
    "https://example.com/p?keep=9", ["fb_cid", "fb_asid", "fb_aid"])

url("strips placement when ad params are present alongside it",
    "https://example.com/p?fb_cid=1&placement=Facebook_Desktop_Feed&sku=4",
    "https://example.com/p?sku=4", ["fb_cid", "placement"])

url("keeps placement when nothing else marks the url as an ad link",
    "https://jobs.example.com/search?placement=remote&level=senior",
    "https://jobs.example.com/search?placement=remote&level=senior", [])

url("keeps pid and c on an ordinary shop url",
    "https://shop.example.com/i?pid=88512&c=3&color=red",
    "https://shop.example.com/i?pid=88512&c=3&color=red", [])

url("strips adguard-sourced analytics params",
    "https://example.com/p?__hstc=a&__hssc=b&_ga=c&_openstat=d&keep=1",
    "https://example.com/p?keep=1", ["__hstc", "__hssc", "_ga", "_openstat"])

url("does not let the fb_ prefix swallow an unrelated fb param",
    "https://example.com/p?fbi=1&fb=2", "https://example.com/p?fbi=1&fb=2", [])

if FAILURES:
  print("FAIL: %d of the checks did not pass\n" % len(FAILURES))
  print("\n\n".join(FAILURES))
  sys.exit(1)

print("ok - all checks passed")
