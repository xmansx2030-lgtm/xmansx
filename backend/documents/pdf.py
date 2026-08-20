"""محرك توليد PDF — HTML+CSS ← WeasyPrint (البنود 46-53).

لماذا WeasyPrint: تشكيل عربي واتجاه RTL عبر Pango/HarfBuzz/FriBidi (لا إعادة
تشكيل يدوية)، ودعم CSS للطباعة الحقيقي (‏`@page`, `page-break`, تكرار
`thead` على الصفحات، هوامش وترويسة/تذييل)، ويعمل داخل الحاوية بمكتبات نظام
مثبتة في `backend/Dockerfile` وخطوط Noto (رخصة OFL) — لا ملفات خطوط في المستودع.

الاستيراد **كسول**: مسار Windows للتطوير بلا مكتبات GTK لا يجب أن يكسر استيراد
النماذج أو تشغيل بقية الاختبارات؛ التوليد نفسه يتم في الحاوية.
"""

import logging

logger = logging.getLogger("xmansx.documents")

MIME_PDF = "application/pdf"


class PdfEngineUnavailable(RuntimeError):
    """المحرك غير مثبت في هذه البيئة — المستند لا يعتبر جاهزًا (البند 120)."""


def _weasyprint():
    try:
        import weasyprint  # noqa: PLC0415 — استيراد كسول مقصود
    except OSError as exc:  # مكتبات النظام ناقصة (Pango/Cairo)
        raise PdfEngineUnavailable(str(exc)) from exc
    except ImportError as exc:
        raise PdfEngineUnavailable(str(exc)) from exc
    return weasyprint


def pdf_engine_available() -> bool:
    try:
        _weasyprint()
    except PdfEngineUnavailable:
        return False
    return True


def render_pdf(html: str) -> bytes:
    """يحول HTML مكتملًا إلى بايتات PDF.

    ‏`base_url=None` متعمد: لا يسمح للقالب بجلب أي مورد خارجي أو محلي بالمسار،
    فالمستند مكتفٍ بذاته ولا يمكن استغلاله لقراءة ملفات النظام (path traversal).
    """
    weasyprint = _weasyprint()
    return weasyprint.HTML(string=html).write_pdf()


def render_pdf_with_pages(html: str) -> tuple[bytes, int]:
    """نفس التوليد مع عدد الصفحات — للقياس والتحقق بلا إعادة تحليل الملف."""
    weasyprint = _weasyprint()
    document = weasyprint.HTML(string=html).render()
    return document.write_pdf(), len(document.pages)
