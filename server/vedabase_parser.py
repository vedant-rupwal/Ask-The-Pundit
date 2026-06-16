import re
from bs4 import BeautifulSoup

SOURCE_REF_PATTERNS = [
    re.compile(
        r"(Śrīmad-Bhāgavatam|Srimad-Bhagavatam)\s+\d+(?:\.\d+){1,2}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(Bhagavad-gītā|Bhagavad-gita)\s+\d+\.\d+",
        re.IGNORECASE,
    ),
    re.compile(
        r"(Śrī Īśopaniṣad|Sri Isopanisad)\s+\d+",
        re.IGNORECASE,
    ),
    re.compile(r"Teachings of Lord Kapila,?\s+Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Nectar of Devotion,?\s+Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"Science of Self-Realization,?\s+Chapter\s+\d+", re.IGNORECASE),
]

def extract_source_ref(text):
    references = []
    for pattern in SOURCE_REF_PATTERNS:
        references.extend(match.group(0) for match in pattern.finditer(text))

    unique_references = []
    for reference in references:
        if reference not in unique_references:
            unique_references.append(reference)

    if not unique_references:
        return None

    return "; ".join(unique_references)

def process_vedabase_page(html_content, book_title, chapter_num, verse_num):
    """
    Process a Vedabase page and extract verse content.
    
    UPDATED: Now handles verse_num as a list to support range deduplication.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    extracted_items = []

    verse_label = None
    if verse_num is not None:
        if isinstance(verse_num, list):
            if len(verse_num) > 1:
                verse_label = f"{min(verse_num)}-{max(verse_num)}"
            elif len(verse_num) == 1:
                verse_label = str(verse_num[0])
        else:
            verse_label = str(verse_num)

    translation_copy = soup.select_one(".av-translation .copy")
    synonyms_copy = soup.select_one(".av-synonyms .copy")
    translation_text = ""

    core_parts = []
    for element in (translation_copy, synonyms_copy):
        if element:
            text = element.get_text(" ", strip=True)
            if text:
                if element == translation_copy:
                    translation_text = text
                core_parts.append(text)

    if core_parts:
        core_text = "\n\n".join(core_parts)
        core_metadata = {
            "book_title": book_title,
            "chapter_num": chapter_num,
            "type": "Core Verse",
        }
        if verse_label is not None:
            core_metadata["verse_num"] = verse_label
        
        core_source_ref = extract_source_ref(core_text)
        if core_source_ref:
            core_metadata["source_ref"] = core_source_ref

        extracted_items.append({
            "page_content": core_text,
            "metadata": core_metadata,
        })

    purport_section = soup.select_one(".av-purport")
    purport_blocks = purport_section.select(".copy") if purport_section else []
    
    if not purport_blocks and not purport_section:
        translation_seen = translation_copy is None
        for block in soup.select(".copy"):
            if not translation_seen:
                if block == translation_copy:
                    translation_seen = True
                continue
            if block == synonyms_copy:
                continue
            purport_blocks.append(block)

    translation_excerpt = translation_text
    for index, block in enumerate(purport_blocks, start=1):
        paragraph_text = block.get_text(" ", strip=True)
        if not paragraph_text:
            continue

        purport_content = f"Context: {translation_excerpt} | Purport: {paragraph_text}" if translation_excerpt else f"Purport: {paragraph_text}"

        purport_metadata = {
            "book_title": book_title,
            "chapter_num": chapter_num,
            "type": "Purport",
            "paragraph": index,
        }
        if verse_label is not None:
            purport_metadata["verse_num"] = verse_label
            
        source_ref = extract_source_ref(paragraph_text)
        if source_ref:
            purport_metadata["source_ref"] = source_ref

        extracted_items.append({
            "page_content": purport_content,
            "metadata": purport_metadata,
        })

    return extracted_items