#!/usr/bin/env python3
"""
build_hub.py -- wraps the 4 standalone page fragments (dfs_page.html,
impact_page.html, diversions_page.html, props_page.html) into one hub
artifact with a tab bar + an iframe per page (base64-encoded into
srcdoc), so each page's own CSS/JS stays fully isolated -- no risk of
collisions between e.g. the two pages that both declare `const DATA =`.
"""
import base64
import os

# Page fragments live next to this script. Override with PAGES_DIR to build
# from a working copy elsewhere (e.g. a session scratchpad).
SCRATCH = os.environ.get("PAGES_DIR", os.path.dirname(os.path.abspath(__file__))).rstrip("/") + "/"

TABS = [
    ("dfs", "DFS Lab", "dfs_page.html"),
    ("impact", "Player Impact", "impact_page.html"),
    ("props", "Prop Board", "props_page.html"),
    ("diversions", "Line Diversions", "diversions_page.html"),
]

def wrap_full_doc(fragment):
    return ('<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"></head>\n'
            + fragment + '\n</html>')

b64_blocks = []
tab_buttons = []
for key, label, fname in TABS:
    fragment = open(SCRATCH + fname, encoding="utf-8").read()
    full_doc = wrap_full_doc(fragment)
    b64 = base64.b64encode(full_doc.encode("utf-8")).decode("ascii")
    b64_blocks.append(f'<script type="text/plain" id="src-{key}">{b64}</script>')
    tab_buttons.append((key, label))
    print(f"{label}: {len(full_doc):,} bytes -> {len(b64):,} base64 chars")

tab_button_html = "\n".join(
    f'      <button class="tab" data-key="{key}" onclick="showTab(\'{key}\')">{label}</button>'
    for key, label in tab_buttons
)

hub = f"""<title>CFB Betting Hub</title>
<style>
  :root {{
    --ink: #0a0e1a;
    --paper: #0a0e1a;
    --paper-2: #090d1f;
    --line: rgba(255,255,255,0.2);
    --text: #ffffff;
    --text-dim: #9ca3af;
    --accent: #7ab3f0;
    --surface: #0d1225;
    --surface-2: #141b30;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; background: var(--paper); }}
  body {{
    display: flex; flex-direction: column;
    font-family: 'Barlow Condensed', Helvetica, Arial, sans-serif;
    color: var(--text);
  }}
  .bar {{
    display: flex; align-items: center; gap: 4px;
    padding: 0 16px; height: 52px; min-height: 52px;
    background: var(--paper-2); border-bottom: 1px solid var(--line);
    overflow-x: auto; overflow-y: hidden; -webkit-overflow-scrolling: touch;
  }}
  .brand {{
    font-weight: 800; font-size: 15px; letter-spacing: 0.04em; text-transform: uppercase;
    color: var(--text); white-space: nowrap; padding-right: 16px;
    border-right: 1px solid var(--line); margin-right: 8px;
  }}
  .tab {{
    appearance: none; background: transparent; border: 0;
    color: var(--text-dim); font-family: inherit; font-weight: 600; font-size: 14px;
    letter-spacing: 0.02em; text-transform: uppercase;
    padding: 0 14px; height: 52px; white-space: nowrap; cursor: pointer;
    border-bottom: 3px solid transparent;
  }}
  .tab:hover {{ color: var(--text); }}
  .tab.active {{ color: var(--text); border-bottom-color: var(--accent); }}
  .frame-wrap {{ flex: 1; position: relative; min-height: 0; }}
  iframe {{
    position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: none;
    background: var(--paper);
  }}
  iframe.active {{ display: block; }}
</style>
<div class="bar">
  <span class="brand">CFB&nbsp;Betting&nbsp;Hub</span>
{tab_button_html}
</div>
<div class="frame-wrap" id="frameWrap"></div>

{chr(10).join(b64_blocks)}

<script>
  var loaded = {{}};
  function showTab(key) {{
    document.querySelectorAll('.tab').forEach(function(b) {{
      b.classList.toggle('active', b.dataset.key === key);
    }});
    document.querySelectorAll('iframe').forEach(function(f) {{
      f.classList.toggle('active', f.dataset.key === key);
    }});
    if (!loaded[key]) {{
      var b64 = document.getElementById('src-' + key).textContent;
      var html = decodeURIComponent(escape(atob(b64)));
      var iframe = document.createElement('iframe');
      iframe.dataset.key = key;
      iframe.className = 'active';
      iframe.srcdoc = html;
      document.getElementById('frameWrap').appendChild(iframe);
      loaded[key] = true;
    }}
  }}
  showTab('{tab_buttons[0][0]}');
</script>
"""

out_path = SCRATCH + "hub_page.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(hub)
print(f"\nWrote {out_path}: {len(hub):,} bytes")
