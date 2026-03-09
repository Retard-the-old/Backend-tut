def wrap(content_html: str, preview_text: str = "") -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body{{margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif}}
.c{{max-width:600px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden}}
.h{{background:#1B4F72;padding:24px 32px;text-align:center}}
.h h1{{color:#fff;margin:0;font-size:28px;letter-spacing:1px}}
.b{{padding:32px;color:#1C2833;font-size:15px;line-height:1.7}}
.b h2{{color:#1B4F72;font-size:20px;margin-top:0}}
.hl{{background:#D6EAF8;padding:16px;border-radius:6px;margin:16px 0}}
.f{{background:#f4f6f8;padding:20px 32px;text-align:center;font-size:12px;color:#5D6D7E}}
</style></head><body>
<span style="display:none;font-size:0;color:#f4f6f8">{preview_text}</span>
<div class="c"><div class="h"><h1>Tutorii</h1></div>
<div class="b">{content_html}</div>
<div class="f">&copy; 2026 Tutorii &middot; AI-Powered Tutoring</div>
</div></body></html>"""
