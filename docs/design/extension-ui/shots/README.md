# Mockup screenshots

The PNG images in this folder come from the script `scripts/dev/render_design_shots.py`, not by hand.
Each mockup `*.html` in `docs/design/extension-ui/` gets two narrow-width screenshots:
`<name>-light.png` and `<name>-dark.png`.

Regenerate them with a local headless Chrome (`google-chrome`, `chromium` or `chromium-browser` on PATH):

```sh
python3 scripts/dev/render_design_shots.py docs/design/extension-ui
```

The script opens each page as a `file://` URL and makes no network requests.
