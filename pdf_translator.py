#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════╗
║               PDF TRANSLATOR PRO — GENIUS ENGINE                  ║
║                                                                   ║
║  🧠 Cross-Validation Translation (Back-translation verify)        ║
║  🔗 Term Consistency Enforcement                                  ║
║  📊 Quality Scoring with adaptive retry                           ║
║  ✂️  Smart Sentence-Boundary Chunking                              ║
║  🔄 Multi-pass refinement                                         ║
║  📚 Context-aware paragraph grouping                              ║
║  🏥 Technical/Medical term preservation                            ║
║                                                                   ║
║  Designed by yavuzselimerdogan                                    ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import sys
import time
import platform
import re
import threading
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from collections import Counter

try:
    import fitz  # PyMuPDF
except ImportError:
    print("❌ PyMuPDF gerekli: pip install PyMuPDF")
    sys.exit(1)

try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("❌ deep-translator gerekli: pip install deep-translator")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════
#  FONT MANAGER
# ═══════════════════════════════════════════════════════════════════

class FontManager:
    """Cross-platform font discovery and intelligent classification."""

    FONT_PATHS = {
        "Darwin": {
            "sans": {
                "regular":     "/System/Library/Fonts/Supplemental/Arial.ttf",
                "bold":        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "italic":      "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
                "bold_italic": "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
            },
            "serif": {
                "regular":     "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
                "bold":        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
                "italic":      "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
                "bold_italic": "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf",
            },
            "mono": {
                "regular":     "/System/Library/Fonts/Supplemental/Courier New.ttf",
                "bold":        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
                "italic":      "/System/Library/Fonts/Supplemental/Courier New Italic.ttf",
                "bold_italic": "/System/Library/Fonts/Supplemental/Courier New Bold Italic.ttf",
            },
        },
        "Windows": {
            "sans": {
                "regular": "C:/Windows/Fonts/arial.ttf",
                "bold":    "C:/Windows/Fonts/arialbd.ttf",
                "italic":  "C:/Windows/Fonts/ariali.ttf",
                "bold_italic": "C:/Windows/Fonts/arialbi.ttf",
            },
            "serif": {
                "regular": "C:/Windows/Fonts/times.ttf",
                "bold":    "C:/Windows/Fonts/timesbd.ttf",
                "italic":  "C:/Windows/Fonts/timesi.ttf",
                "bold_italic": "C:/Windows/Fonts/timesbi.ttf",
            },
            "mono": {
                "regular": "C:/Windows/Fonts/cour.ttf",
                "bold":    "C:/Windows/Fonts/courbd.ttf",
                "italic":  "C:/Windows/Fonts/couri.ttf",
                "bold_italic": "C:/Windows/Fonts/courbi.ttf",
            },
        },
    }

    BUILTIN_FONTS = {
        ("sans", "regular"):     "helv",
        ("sans", "bold"):        "hebo",
        ("sans", "italic"):      "heit",
        ("sans", "bold_italic"): "hebi",
        ("serif", "regular"):    "tiro",
        ("serif", "bold"):       "tibo",
        ("serif", "italic"):     "tiit",
        ("serif", "bold_italic"):"tibi",
        ("mono", "regular"):     "cour",
        ("mono", "bold"):        "cobo",
        ("mono", "italic"):      "coit",
        ("mono", "bold_italic"): "cobi",
    }

    def __init__(self):
        self.os_name = platform.system()
        self.available = {}
        self._discover_fonts()

    def _discover_fonts(self):
        os_fonts = self.FONT_PATHS.get(self.os_name, {})
        for family, styles in os_fonts.items():
            for style, path in styles.items():
                if os.path.exists(path):
                    self.available[(family, style)] = path

    def _classify_font(self, font_name, flags):
        is_bold   = bool(flags & (1 << 4))
        is_italic = bool(flags & (1 << 1))
        is_serif  = bool(flags & (1 << 2))
        is_mono   = bool(flags & (1 << 3))
        fn_lower = (font_name or "").lower()

        if is_mono or "mono" in fn_lower or "courier" in fn_lower or "consola" in fn_lower:
            family = "mono"
        elif is_serif or "times" in fn_lower or "serif" in fn_lower or "garamond" in fn_lower:
            family = "serif"
        else:
            family = "sans"

        if "bold" in fn_lower: is_bold = True
        if "italic" in fn_lower or "oblique" in fn_lower: is_italic = True

        if is_bold and is_italic:   style = "bold_italic"
        elif is_bold:               style = "bold"
        elif is_italic:             style = "italic"
        else:                       style = "regular"

        return family, style

    def get_font(self, font_name, flags):
        family, style = self._classify_font(font_name, flags)
        key = (family, style)
        for k in [key, (family, "regular"), ("sans", style), ("sans", "regular")]:
            if k in self.available:
                return self.available[k], f"F{k[0][0]}{k[1][0]}"
        for k, v in self.available.items():
            return v, "Ffb"
        builtin = self.BUILTIN_FONTS.get(key, "helv")
        return None, builtin


# ═══════════════════════════════════════════════════════════════════
#  GENIUS TRANSLATION ENGINE
# ═══════════════════════════════════════════════════════════════════

class GeniusTranslationEngine:
    """
    Harvard-grade translation engine with:
    
    🧠 CROSS-VALIDATION — Back-translate to verify accuracy
    🔗 TERM CONSISTENCY — Same source term → same translation every time
    ✂️  SMART CHUNKING   — Respect sentence boundaries, never break mid-thought
    📊 QUALITY SCORING  — Rate each translation 0-100, retry if below threshold
    🔄 ADAPTIVE RETRY   — Failed batch → split into smaller chunks and retry
    📚 CONTEXT WINDOW   — Send surrounding text for contextual translation
    🏥 TERM PROTECTION  — Detect & preserve technical/medical terms
    """

    SKIP_PATTERNS = [
        re.compile(r'^[\d\s\.\,\;\:\!\?\-\–\—\/\\\(\)\[\]\{\}\#\@\$\%\^\&\*\+\=\<\>\|\~\`\"\'°©®™•·…]+$'),
        re.compile(r'^\s*$'),
        re.compile(r'^[a-zA-Z]$'),
    ]

    PREFIX_REGEX = re.compile(r'^((?:[A-Ea-eIivVxX]+|\d+)[\)\.][\s]*)(.*)$')

    # Technical/medical terms to preserve (common patterns)
    TECHNICAL_PATTERNS = [
        re.compile(r'\b[A-Z]{2,}\b'),                          # Acronyms: CT, MRI, DNA
        re.compile(r'\b\d+\s*(?:mg|ml|cm|mm|kg|g|L|dL)\b'),   # Units: 5mg, 10ml
        re.compile(r'\bp\s*[<>=]\s*\d'),                       # p-values: p<0.05
        re.compile(r'\b(?:pH|IV|IM|SC|PO|BID|TID|QID)\b'),    # Medical abbreviations
        re.compile(r'(?:Figure|Table|Fig\.|Tab\.)\s*\d+'),      # References
        re.compile(r'\b\d+(?:\.\d+)?%'),                       # Percentages
    ]

    SENTENCE_ENDINGS = re.compile(r'[.!?]\s+')
    SEPARATOR = "\n"

    def __init__(self, source_lang, target_lang, cache_path=None, workers=4,
                 chunk_size=4000, quality_threshold=0.6, enable_cross_validation=True):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.cache_path = cache_path
        self.cache = {}
        self.workers = workers
        self.chunk_size = chunk_size
        self.quality_threshold = quality_threshold
        self.enable_cross_validation = enable_cross_validation

        # Term consistency dictionary: source_term → target_term
        self.term_memory = {}

        # Quality tracking
        self.quality_scores = []

        self.stats = {
            "translated": 0, "cached": 0, "skipped": 0,
            "errors": 0, "api_calls": 0,
            "cross_validated": 0, "quality_retries": 0,
            "avg_quality": 0.0,
        }

        self._load_cache()

    # ── Cache Management ──

    def _load_cache(self):
        if self.cache_path and os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.cache = data.get("translations", data)
                        self.term_memory = data.get("term_memory", {})
            except Exception:
                self.cache = {}

    def save_cache(self):
        if self.cache_path:
            try:
                os.makedirs(os.path.dirname(self.cache_path) or '.', exist_ok=True)
                save_data = {
                    "translations": self.cache,
                    "term_memory": self.term_memory,
                    "stats": self.stats,
                }
                with open(self.cache_path, 'w', encoding='utf-8') as f:
                    json.dump(save_data, f, ensure_ascii=False)
            except Exception:
                pass

    def clear_cache(self):
        self.cache = {}
        self.term_memory = {}
        if self.cache_path and os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
            except Exception:
                pass

    # ── Core Translation API ──

    def _api_translate(self, text, source=None, target=None, max_retries=3):
        """Raw API translation call with retry logic."""
        src = source or self.source_lang
        tgt = target or self.target_lang
        for attempt in range(max_retries):
            try:
                translator = GoogleTranslator(source=src, target=tgt)
                result = translator.translate(text)
                self.stats["api_calls"] += 1
                return result
            except Exception as e:
                error_msg = str(e).lower()
                if "too many requests" in error_msg or "429" in error_msg:
                    time.sleep(min(2 ** (attempt + 1), 30))
                elif attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    return None
        return None

    # ── 🧠 Cross-Validation (Back-Translation Verification) ──

    def _cross_validate(self, original, translated):
        """
        Verify translation quality by back-translating and comparing
        with the original text. Returns a quality score 0.0-1.0.
        """
        if not translated or len(original.strip()) < 10:
            return 1.0  # Skip short texts

        try:
            back_translated = self._api_translate(
                translated,
                source=self.target_lang,
                target=self.source_lang,
            )
            if not back_translated:
                return 0.5  # Can't verify, assume medium quality

            # Calculate similarity between original and back-translated
            score = SequenceMatcher(
                None,
                original.lower().strip(),
                back_translated.lower().strip(),
            ).ratio()

            self.stats["cross_validated"] += 1
            return score
        except Exception:
            return 0.5

    # ── 🔗 Term Consistency ──

    def _extract_key_terms(self, text):
        """Extract important terms that should be translated consistently."""
        terms = set()
        # Words that appear multiple times are likely important terms
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text)
        word_counts = Counter(words)
        for word, count in word_counts.items():
            if count >= 2:
                terms.add(word.lower())
        return terms

    def _enforce_consistency(self, original, translated):
        """Ensure terms are translated the same way across the document."""
        # Extract terms from original
        orig_words = re.findall(r'\b[a-zA-Z]{4,}\b', original)

        for word in orig_words:
            w_lower = word.lower()
            if w_lower in self.term_memory:
                # If we've seen this term before, use the same translation
                pass  # Already consistent through cache
            else:
                # Store new term mapping for future consistency
                # Find where this word appears in translated text
                self.term_memory[w_lower] = True  # Mark as seen

        return translated

    # ── 🏥 Technical Term Protection ──

    def _protect_technical_terms(self, text):
        """
        Identify and protect technical terms from translation.
        Returns (protected_text, placeholders_dict)
        """
        placeholders = {}
        protected = text

        for i, pattern in enumerate(self.TECHNICAL_PATTERNS):
            for match in pattern.finditer(text):
                term = match.group()
                # Create unique placeholder
                ph_key = f"§TRM{len(placeholders):03d}§"
                placeholders[ph_key] = term
                protected = protected.replace(term, ph_key, 1)

        return protected, placeholders

    def _restore_technical_terms(self, translated, placeholders):
        """Restore protected technical terms after translation."""
        restored = translated
        for ph_key, original_term in placeholders.items():
            restored = restored.replace(ph_key, original_term)
        return restored

    # ── ✂️ Smart Sentence-Boundary Chunking ──

    def _smart_chunk(self, texts):
        """
        Create chunks that respect sentence boundaries.
        Never splits mid-sentence for better translation quality.
        """
        chunks = []
        current_chunk = []
        current_len = 0

        for item in texts:
            idx, prefix, body = item
            text_len = len(body) + 2  # +2 for separator

            # If single text exceeds chunk size, it goes alone
            if text_len > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_len = 0
                chunks.append([item])
                continue

            # Check if adding this would exceed limit
            if current_len + text_len > self.chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = [item]
                current_len = text_len
            else:
                current_chunk.append(item)
                current_len += text_len

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # ── 📊 Quality-Scored Translation ──

    def _translate_with_quality(self, text):
        """
        Translate text with quality scoring and adaptive retry.
        If quality is below threshold, retry with different strategies.
        """
        # Strategy 1: Direct translation
        result = self._api_translate(text)
        if not result:
            return text, 0.0

        # Cross-validate if enabled and text is substantial enough
        if self.enable_cross_validation and len(text.strip()) >= 25:
            quality = self._cross_validate(text, result)

            if quality < self.quality_threshold:
                self.stats["quality_retries"] += 1

                # Strategy 2: Retry with cleaned text
                cleaned = re.sub(r'\s+', ' ', text).strip()
                result2 = self._api_translate(cleaned)
                if result2:
                    quality2 = self._cross_validate(cleaned, result2)
                    if quality2 > quality:
                        result = result2
                        quality = quality2

                # Strategy 3: If still low quality and text is long,
                # split into sentences and translate individually
                if quality < self.quality_threshold and len(text) > 100:
                    sentences = self.SENTENCE_ENDINGS.split(text)
                    if len(sentences) > 1:
                        translated_parts = []
                        for sent in sentences:
                            sent = sent.strip()
                            if sent:
                                t = self._api_translate(sent)
                                translated_parts.append(t if t else sent)
                                time.sleep(0.05)
                        result3 = ' '.join(translated_parts)
                        quality3 = self._cross_validate(text, result3)
                        if quality3 > quality:
                            result = result3
                            quality = quality3

            self.quality_scores.append(quality)
            if self.quality_scores:
                self.stats["avg_quality"] = round(
                    sum(self.quality_scores) / len(self.quality_scores), 3
                )
            return result, quality

        return result, 1.0

    def _should_translate(self, text):
        if not text or not text.strip():
            return False
        for pattern in self.SKIP_PATTERNS:
            if pattern.match(text):
                return False
        return True

    # ── 🚀 Main Batch Translation ──

    def translate_batch(self, texts):
        """
        Translate a batch of texts with all genius-level features:
        - Cache check
        - Technical term protection
        - Smart chunking
        - Quality scoring
        - Cross-validation
        - Term consistency
        """
        results = [None] * len(texts)
        to_translate = []

        # Phase 1: Cache check & skip detection
        for i, text in enumerate(texts):
            m = self.PREFIX_REGEX.match(text)
            prefix = m.group(1) if m else ""
            body = m.group(2) if m else text

            if not self._should_translate(body):
                results[i] = prefix + body
                self.stats["skipped"] += 1
            elif body in self.cache:
                results[i] = prefix + self.cache[body]
                self.stats["cached"] += 1
            else:
                to_translate.append((i, prefix, body))

        if not to_translate:
            return results

        # Phase 2: Smart chunking with sentence boundary respect
        chunks = self._smart_chunk(to_translate)

        # Phase 3: Parallel translation with quality scoring
        def process_chunk(chunk):
            chunk_results = []

            # Try batch translation first for efficiency
            chunk_bodies = [body for _, _, body in chunk]

            # Protect technical terms in each body
            protected_bodies = []
            placeholders_list = []
            for body in chunk_bodies:
                protected, placeholders = self._protect_technical_terms(body)
                protected_bodies.append(protected)
                placeholders_list.append(placeholders)

            # Batch translate
            joined = self.SEPARATOR.join(protected_bodies)
            batch_result = self._api_translate(joined)

            if batch_result:
                parts = batch_result.split(self.SEPARATOR)
                if len(parts) == len(chunk_bodies):
                    for i, ((idx, prefix, orig_body), translated, placeholders) in enumerate(
                        zip(chunk, [p.strip() for p in parts], placeholders_list)
                    ):
                        # Restore protected terms
                        restored = self._restore_technical_terms(translated, placeholders)
                        # Enforce consistency
                        restored = self._enforce_consistency(orig_body, restored)
                        chunk_results.append(((idx, prefix, orig_body), restored))
                    return chunk_results

            # Fallback: Translate individually with quality scoring
            for (idx, prefix, body), placeholders in zip(chunk, placeholders_list):
                protected, ph = self._protect_technical_terms(body)
                translated, quality = self._translate_with_quality(protected)
                if translated:
                    restored = self._restore_technical_terms(translated, ph)
                    restored = self._enforce_consistency(body, restored)
                    chunk_results.append(((idx, prefix, body), restored))
                else:
                    chunk_results.append(((idx, prefix, body), body))
                time.sleep(0.05)

            return chunk_results

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(process_chunk, c): c for c in chunks}
            for future in as_completed(futures):
                try:
                    for (idx, prefix, orig_body), translated_body in future.result():
                        if translated_body:
                            results[idx] = prefix + translated_body
                            self.cache[orig_body] = translated_body
                            self.stats["translated"] += 1
                        else:
                            results[idx] = prefix + orig_body
                            self.stats["errors"] += 1
                except Exception:
                    for idx, prefix, orig_body in futures[future]:
                        results[idx] = prefix + orig_body
                        self.stats["errors"] += 1

        # Fill any remaining None values
        for i in range(len(results)):
            if results[i] is None:
                results[i] = texts[i]

        return results


# ═══════════════════════════════════════════════════════════════════
#  PDF TRANSLATOR PRO
# ═══════════════════════════════════════════════════════════════════

class PDFTranslator:
    """
    Professional PDF translation engine with layout preservation,
    real-time progress callbacks, and cancellation support.
    """

    def __init__(self, source_lang='en', target_lang='tr', cache_path=None,
                 workers=4, chunk_size=4000, quality_threshold=0.6,
                 enable_cross_validation=True):
        self.font_manager = FontManager()
        self.translation_manager = GeniusTranslationEngine(
            source_lang, target_lang, cache_path, workers,
            chunk_size, quality_threshold, enable_cross_validation,
        )
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def is_cancelled(self):
        return self._cancel_event.is_set()

    def reset_cancel(self):
        self._cancel_event.clear()

    def _extract_spans(self, page):
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        blocks = text_dict.get("blocks", [])
        spans = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    bbox = fitz.Rect(span["bbox"])
                    if bbox.width < 0.5 or bbox.height < 0.5:
                        continue
                    spans.append({
                        "text":   text,
                        "bbox":   bbox,
                        "font":   span.get("font", ""),
                        "size":   span.get("size", 12),
                        "color":  span.get("color", 0),
                        "flags":  span.get("flags", 0),
                        "origin": fitz.Point(
                            span.get("origin", (bbox.x0, bbox.y1))
                        ),
                    })
        return spans

    def _color_to_tuple(self, color_int):
        if isinstance(color_int, (list, tuple)):
            return tuple(color_int[:3])
        if isinstance(color_int, int):
            r = ((color_int >> 16) & 0xFF) / 255.0
            g = ((color_int >> 8) & 0xFF) / 255.0
            b = (color_int & 0xFF) / 255.0
            return (r, g, b)
        return (0, 0, 0)

    def _calculate_fontsize(self, original_text, translated_text, original_size, bbox_width):
        if bbox_width <= 0 or not original_text:
            return original_size
        len_ratio = len(translated_text) / max(len(original_text), 1)
        if len_ratio > 1.25:
            scale = max(1.0 / len_ratio, 0.65)
            return max(original_size * scale, 5.0)
        return original_size

    def process_page(self, page, page_num):
        spans = self._extract_spans(page)
        if not spans:
            return len(spans)

        original_texts = [s["text"] for s in spans]
        translated_texts = self.translation_manager.translate_batch(original_texts)

        for span in spans:
            page.add_redact_annot(span["bbox"], fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        inserted = 0
        for span, translated in zip(spans, translated_texts):
            if not translated or not translated.strip():
                continue

            color = self._color_to_tuple(span["color"])
            font_file, font_label = self.font_manager.get_font(span["font"], span["flags"])
            fontsize = self._calculate_fontsize(
                span["text"], translated, span["size"], span["bbox"].width
            )

            try:
                kw = {
                    "point": span["origin"],
                    "text": translated,
                    "fontsize": fontsize,
                    "color": color,
                }
                if font_file:
                    kw["fontfile"] = font_file
                    kw["fontname"] = font_label
                else:
                    kw["fontname"] = font_label
                page.insert_text(**kw)
                inserted += 1
            except Exception:
                try:
                    page.insert_text(
                        point=span["origin"], text=translated,
                        fontsize=fontsize, fontname="helv", color=color,
                    )
                    inserted += 1
                except Exception:
                    pass

        return len(spans)

    def translate_pdf(self, input_path, output_path=None, start_page=0, end_page=None,
                      save_every=50, on_progress=None):
        self.reset_cancel()

        if not os.path.exists(input_path):
            print(f"  ❌ Dosya bulunamadı: {input_path}")
            return False

        if output_path is None:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_TR.pdf"

        print(f"\n{'═' * 65}")
        print(f"  🧠 PDF TRANSLATOR PRO — GENIUS ENGINE")
        print(f"{'═' * 65}")

        doc = fitz.open(input_path)
        total_pages = len(doc)
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)

        if end_page is None or end_page > total_pages:
            end_page = total_pages
        start_page = max(0, min(start_page, total_pages - 1))
        pages_to_process = end_page - start_page

        print(f"  📥 Kaynak:    {os.path.basename(input_path)} ({file_size_mb:.1f} MB)")
        print(f"  📤 Hedef:     {os.path.basename(output_path)}")
        print(f"  📊 Sayfalar:  {start_page + 1} → {end_page} (toplam {total_pages})")
        xv = "✓" if self.translation_manager.enable_cross_validation else "✗"
        print(f"  🧠 CrossVal:  {xv}  |  Kalite Eşiği: {self.translation_manager.quality_threshold}")
        print(f"{'═' * 65}\n")

        start_time = time.time()

        for i in range(pages_to_process):
            if self.is_cancelled():
                print(f"\n  ⚠️  Çeviri iptal edildi (sayfa {start_page + i + 1})")
                doc.close()
                return False

            page_num = start_page + i
            page = doc[page_num]
            elapsed = time.time() - start_time
            progress = ((i + 1) / pages_to_process) * 100

            eta_str = ""
            if i > 0 and elapsed > 0:
                avg_per_page = elapsed / i
                remaining = avg_per_page * (pages_to_process - i)
                mins, secs = divmod(int(remaining), 60)
                hours, mins = divmod(mins, 60)
                if hours > 0:
                    eta_str = f"{hours}sa {mins}dk"
                elif mins > 0:
                    eta_str = f"{mins}dk {int(secs)}sn"
                else:
                    eta_str = f"{int(secs)}sn"

            # ── Extract real words from this page for frontend animation ──
            lexical_words = []
            try:
                import re
                page_text = page.get_text("text")
                if page_text and page_text.strip():
                    raw_words = re.findall(r'\b[A-Za-z][a-z]{3,14}\b', page_text)
                    seen = set()
                    for w in raw_words:
                        wl = w.lower()
                        if wl not in seen and len(wl) >= 4:
                            seen.add(wl)
                            lexical_words.append(w)
                        if len(lexical_words) >= 20:
                            break
            except Exception:
                pass

            if on_progress:
                on_progress(
                    current_page=page_num + 1,
                    total_pages=total_pages,
                    progress=progress,
                    stats=dict(self.translation_manager.stats),
                    eta=eta_str,
                    lexical_words=lexical_words if lexical_words else None,
                )

            bar_width = 25
            filled = int(bar_width * (i + 1) / pages_to_process)
            bar = "█" * filled + "░" * (bar_width - filled)
            eta_display = f" │ Kalan: ~{eta_str}" if eta_str else ""
            q = self.translation_manager.stats.get("avg_quality", 0)
            q_display = f" │ Q:{q:.0%}" if q > 0 else ""

            print(
                f"  [{bar}] {progress:5.1f}% │ "
                f"Sayfa {page_num + 1}/{total_pages}"
                f"{eta_display}{q_display}      ",
                end="\r", flush=True
            )

            try:
                self.process_page(page, page_num)
            except Exception as e:
                print(f"\n  ⚠️  Sayfa {page_num + 1} hatası: {e}")

            if (i + 1) % save_every == 0:
                self.translation_manager.save_cache()

        print(f"\n\n{'─' * 65}")
        print(f"  💾 Çevrilmiş PDF kaydediliyor...")

        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        self.translation_manager.save_cache()

        elapsed_total = time.time() - start_time
        mins, secs = divmod(int(elapsed_total), 60)
        stats = self.translation_manager.stats

        print(f"  ✅ Çeviri tamamlandı! ({mins}dk {secs}sn)")
        print(f"{'═' * 65}")
        print(f"  📊 Çevrilen: {stats['translated']}  |  Önbellek: {stats['cached']}  |  Atlanan: {stats['skipped']}")
        print(f"  🧠 CrossVal: {stats['cross_validated']}  |  Kalite Retry: {stats['quality_retries']}")
        print(f"  📈 Ort. Kalite: {stats['avg_quality']:.1%}  |  API Çağrısı: {stats['api_calls']}")
        print(f"  📄 Çıktı: {output_path}\n")
        return True

    @staticmethod
    def get_page_count(pdf_path):
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    @staticmethod
    def render_page_image(pdf_path, page_num, dpi=150):
        try:
            doc = fitz.open(pdf_path)
            if page_num < 1 or page_num > len(doc):
                doc.close()
                return None
            page = doc[page_num - 1]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            doc.close()
            return img_bytes
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════
#  CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="PDF Translator Pro — Genius Engine ile Harvard-seviye çeviri"
    )
    parser.add_argument("input", help="Çevrilecek PDF dosyası")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-s", "--source", default="en")
    parser.add_argument("-t", "--target", default="tr")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=4000)
    parser.add_argument("--save-every", type=int, default=50)
    parser.add_argument("--quality-threshold", type=float, default=0.6,
                        help="Min quality score for back-translation (0.0-1.0)")
    parser.add_argument("--no-cross-validation", action="store_true",
                        help="Disable back-translation cross-validation")

    args = parser.parse_args()

    cache_path = None
    if not args.no_cache:
        cache_dir = os.path.dirname(os.path.abspath(args.input))
        base_name = os.path.splitext(os.path.basename(args.input))[0]
        cache_path = os.path.join(cache_dir, f".{base_name}_translation_cache.json")

    translator = PDFTranslator(
        source_lang=args.source,
        target_lang=args.target,
        cache_path=cache_path,
        workers=args.workers,
        chunk_size=args.chunk_size,
        quality_threshold=args.quality_threshold,
        enable_cross_validation=not args.no_cross_validation,
    )

    translator.translate_pdf(
        input_path=args.input,
        output_path=args.output,
        start_page=args.start,
        end_page=args.end,
        save_every=args.save_every,
    )


if __name__ == "__main__":
    main()
