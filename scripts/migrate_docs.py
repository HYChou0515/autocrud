import os
import re

DOCS_DIR = "docs"


def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original_content = content

    # 1. Code Blocks: ```{code-block} python or just {code-block}
    # Pattern: ^```{code-block} ?(\w+)?$
    content = re.sub(
        r"^```\{code-block\}\s*(\w+)?", r"```\1", content, flags=re.MULTILINE
    )

    # 2. Version Added
    # ```{versionadded} 0.2.0
    # Description
    # ```
    # Convert to:
    # !!! info "Version added: 0.2.0"
    #     Description
    #
    # Actually, Sphinx syntax usually has content indented or not?
    # Based on observation, it might be inline or block.
    # If it is a block:
    # ```{versionadded} 0.2.0
    # The content
    # ```
    # Replace opening with `!!! info "New in version 0.2.0"` and remove closing ```?
    # But closing ``` matches end of code block too.
    # So I need to match pairs.
    # regex for block: ```{versionadded} (.*?)\n(.*?)```
    # But dotall?

    def repl_version_added(match):
        ver = match.group(1).strip()
        body = match.group(2)
        # Indent body
        body_lines = ["    " + line for line in body.splitlines()]
        return f'!!! info "New in version {ver}"\n' + "\n".join(body_lines)

    content = re.sub(
        r"```\{versionadded\}\s*(.*?)\n(.*?)```",
        repl_version_added,
        content,
        flags=re.DOTALL,
    )

    # Version Changed
    def repl_version_changed(match):
        ver = match.group(1).strip()
        body = match.group(2)
        body_lines = ["    " + line for line in body.splitlines()]
        return f'!!! warning "Changed in version {ver}"\n' + "\n".join(body_lines)

    content = re.sub(
        r"```\{versionchanged\}\s*(.*?)\n(.*?)```",
        repl_version_changed,
        content,
        flags=re.DOTALL,
    )

    # 3. Include
    # ```{include} functions.md
    # ```
    # -> --8<-- "docs/includes/functions.md"
    # Note: Using snippets extension syntax.
    content = re.sub(
        r"```\{include\}\s*(\S+)\s*\n```", r'--8<-- "docs/includes/\1"', content
    )

    # Emphasize lines handling
    # :emphasize-lines: 9
    # -> hl_lines="9"
    # But usually this is inside a code block in Sphinx:
    # ```{code-block} python
    # :emphasize-lines: 9
    #
    # code...
    # ```
    # MkDocs:
    # ```python hl_lines="9"
    # code...
    # ```
    # My previous code block regex might have stripped the directive but left lines.
    # Actually, `content = re.sub(r"^```\{code-block\}\s*(\w+)?", r"```\1", content, flags=re.MULTILINE)`
    # changes ```{code-block} python to ```python.
    # But the next line might be :emphasize-lines: 9.
    # So I need to find ```python\n:emphasize-lines: 9 and merge.

    def repl_emphasize(match):
        lang = match.group(1) or ""
        lines = match.group(2).replace(",", " ")
        return f'```{lang} hl_lines="{lines}"'

    content = re.sub(
        r"^```(\w*)\n:emphasize-lines:\s*(.+)$",
        repl_emphasize,
        content,
        flags=re.MULTILINE,
    )

    # Clean up any remaining {code-block} that might have been missed or malformed
    content = re.sub(
        r"^```\{code-block\}\s*(\w+)?", r"```\1", content, flags=re.MULTILINE
    )

    # Autoclass link
    # .. autoclass:: autocrud.types.ResourceMeta
    # -> [ResourceMeta](../reference/types.md#autocrud.types.ResourceMeta)
    # We can try to be generic: .. autoclass:: autocrud.path.ClassName
    # We need to guess the reference file.
    # Logic: autocrud.types -> reference/types.md
    # autocrud.resource_manager.core -> reference/resource_manager/core.md

    def repl_autoclass(match):
        full_name = match.group(1)
        # Split module and class
        parts = full_name.split(".")
        class_name = parts[-1]

        # remove autocrud prefix if present
        if parts[0] == "autocrud":
            path_parts = parts[1:-1]  # types or resource_manager, core
        else:
            path_parts = parts[:-1]

        # Construct path
        # If autocrud.types -> reference/types.md
        # If autocrud.resource_manager.core -> reference/resource_manager/core.md

        md_path = "/".join(path_parts) + ".md"

        # Calculate relative path from current file
        # This is tricky because calculate relative path needs knowledge of current file location.
        # But we can use absolute path from docs root? No, mkdocs likes relative.
        # Or we can just use the path assuming we are in docs root and let mkdocs resolve?
        # MkDocs warns about relative paths.

        # Let's try to compute relative path.
        rel_to_root = os.path.relpath(
            os.path.join(DOCS_DIR, "reference"), os.path.dirname(filepath)
        )
        link_path = os.path.join(rel_to_root, md_path)

        return f"[{class_name}]({link_path}#{full_name})"

    content = re.sub(r"\.\. autoclass::\s+(\S+)", repl_autoclass, content)

    # Seealso and Generic Admonitions Logic (Procedural)
    admonition_types = [
        "attention",
        "caution",
        "danger",
        "error",
        "hint",
        "important",
        "note",
        "tip",
        "warning",
        "seealso",
    ]

    def transform_admonitions(text):
        lines = text.splitlines()
        new_lines = []
        i = 0

        # Regex to detect start of block
        start_pattern = re.compile(
            r"^(`{3,})\{(" + "|".join(admonition_types) + r")\}\s*(.*)$", re.IGNORECASE
        )

        while i < len(lines):
            line = lines[i]
            match = start_pattern.match(line)
            if match:
                adm_fence = match.group(1)
                adm_type = match.group(2).lower()
                adm_title = match.group(3).strip()
                adm_body = []

                i += 1
                while i < len(lines):
                    check_line = lines[i]
                    # Check for closing fence
                    # Strictly strictly check it matches the opening fence length?
                    # Or at least as long? Sphinx usually uses exact match for end in practice,
                    # but commonmark says closing >= opening.
                    # Let's check for exact match first, then relaxed.
                    if check_line.rstrip() == adm_fence:
                        break
                    adm_body.append(check_line)
                    i += 1

                # Build replacement
                # Indent body
                indented_body = ["    " + b for b in adm_body]

                if adm_title:
                    new_lines.append(f'!!! {adm_type} "{adm_title}"')
                else:
                    new_lines.append(f"!!! {adm_type}")

                new_lines.extend(indented_body)

            else:
                new_lines.append(line)
            i += 1

        return "\n".join(new_lines)

    content = transform_admonitions(content)

    # :material-architecture:
    # -> :material-bank: (architecture is not a valid material icon usually, 'bank' or 'domain' is close)
    # Or maybe the user meant custom icon.
    # Let's assume user wants :material-architecture: to map to :material-domain: for now or check if it exists.
    # Actually commonly used icon for architecture in material design is 'domain' or 'account-balance' (bank).
    # Let's map it.

    content = content.replace(":material-architecture:", ":material-domain:")

    # 4. Termynal
    # ```{termynal}
    # ...
    # ```
    # -> ```console
    content = re.sub(r"^```\{termynal\}", r"```console", content, flags=re.MULTILINE)

    # Generic Admonitions
    # ```{note}
    # ...
    # ```
    # -> !!! note
    #      ...
    admonitions = [
        "attention",
        "caution",
        "danger",
        "error",
        "hint",
        "important",
        "note",
        "tip",
        "warning",
    ]
    admonition_pattern = "|".join(admonitions)

    def repl_admonition(match):
        adm_type = match.group(2).lower()
        title = match.group(3)
        body = match.group(4)

        body_lines = ["    " + line for line in body.splitlines()]

        if title and title.strip():
            return f'!!! {adm_type} "{title.strip()}"\n' + "\n".join(body_lines)
        else:
            return f"!!! {adm_type}\n" + "\n".join(body_lines)

    pattern = r"^(`{3,})\{(" + admonition_pattern + r")\}(.*?)\n(.*?)\n\1"
    content = re.sub(
        pattern,
        repl_admonition,
        content,
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )

    # 5. Images
    # ...

    def repl_image_path(match):
        rel_path = os.path.relpath(filepath, DOCS_DIR)
        depth = len(rel_path.split(os.sep)) - 1
        prefix = "../" * depth if depth > 0 else ""

        alt = match.group(1)
        path = match.group(2)

        # Handle _static
        if "_static/" in path:
            # Replace _static/ with images/ ?
            # And handle relative prefix.
            # Assuming file was in docs/core-concepts/foo.md
            # and image was _static/img.png (relative to source root in Sphinx?)
            # In Sphinx source was docs/source. _static was docs/source/_static.
            # So _static/img.png meant docs/source/_static/img.png.
            # Now images are in docs/images/.
            # docs/core-concepts/foo.md needs path to docs/images/img.png.
            # relative: ../images/img.png
            # So _static/ -> images/ and apply prefix.
            path = path.replace("_static/", "images/")

        if path.startswith("/images/"):
            new_path = prefix + path.lstrip("/")
        elif path.startswith("images/"):
            new_path = prefix + path
        else:
            new_path = path
        return f"![{alt}]({new_path})"

    content = re.sub(r"!\[(.*?)\]\((.*?)\)", repl_image_path, content)

    # 6. HTML Tables in architecture.md cleaning
    # If we see <table class="docutils">...</table> containing mermaid, extract mermaid?
    # This is hard with regex.
    # But we can try to simplify: remove <table>, <tr>, <td>, <tbody> tags?
    # No, that might break structure.
    # Let's just fix the mermaid block inside:
    # <div class="mermaid"> ... </div> -> ```mermaid ... ```

    def repl_mermaid_div(match):
        code = match.group(1)
        return f"```mermaid\n{code}\n```"

    content = re.sub(
        r'<div class="mermaid">\s*(.*?)\s*</div>',
        repl_mermaid_div,
        content,
        flags=re.DOTALL,
    )

    if content != original_content:
        print(f"Fixed {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)


for root, dirs, files in os.walk(DOCS_DIR):
    for name in files:
        if name.endswith(".md"):
            process_file(os.path.join(root, name))
