def entities_to_html(text, entities):
    """
    Преобразует text + entities (из Telegram) в HTML-строку с форматированием.
    """
    if not entities:
        return text

    html = ""
    last_offset = 0
    for entity in sorted(entities, key=lambda e: e.offset):
        # Добавляем текст до entity
        html += text[last_offset:entity.offset]
        entity_text = text[entity.offset:entity.offset + entity.length]
        if entity.type == "bold":
            html += f"<b>{entity_text}</b>"
        elif entity.type == "italic":
            html += f"<i>{entity_text}</i>"
        elif entity.type == "underline":
            html += f"<u>{entity_text}</u>"
        elif entity.type == "strikethrough":
            html += f"<s>{entity_text}</s>"
        elif entity.type == "code":
            html += f"<code>{entity_text}</code>"
        elif entity.type == "pre":
            html += f"<pre>{entity_text}</pre>"
        elif entity.type == "text_link":
            html += f'<a href="{entity.url}">{entity_text}</a>'
        else:
            html += entity_text
        last_offset = entity.offset + entity.length
    # Добавляем оставшийся текст
    html += text[last_offset:]
    return html 