# Copyright 2026 Google LLC

"""Shared build definitions for A2UI mobile web builds."""

def generate_mobile_index_html(name, html_template, js_bundle, out_html):
    """Takes a base HTML template and inline-injects a compiled JS bundle.

    Args:
        name: Name of the generated rule.
        html_template: The base index.html target to use as a shell.
        js_bundle: The compiled JS bundle target (e.g. from closure_js_binary).
        out_html: The filename of the resulting self-contained HTML file.
    """
    native.genrule(
        name = name,
        srcs = [html_template, js_bundle],
        outs = [out_html],
        cmd = """
            # Extract the .js file from the bundle outputs.
            for f in $(locations {js_bundle}); do
                case $$f in *.js) JS_FILE=$$f ;; esac
            done

            # Wrap the raw JS inside <script> tags.
            (
                echo "<script type=\\"text/javascript\\">"
                cat $$JS_FILE
                echo "</script>"
            ) > tmp_inject_js.js

            # Replace the old module <script> tag in index.html with the new injected script.
            sed -e '/<script type="module"/r tmp_inject_js.js' -e '/<script type="module"/d' $(location {html_template}) > $(OUTS)
        """.format(
            html_template = html_template,
            js_bundle = js_bundle,
        ),
    )
