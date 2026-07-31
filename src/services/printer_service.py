"""Business logic for the printer API.

Every public function returns the standardized response shape
(success_response / error_response). Controllers just forward these.

Multiple printers are supported per-request: a print/drawer request may target
any printer by name and override paper settings, instead of relying solely on
the single printer selected from the tray.
"""
import base64

from src.config import TEST_PDF, TEST_LABEL_PDF
from src.services import escpos_service as escpos
from src.services.print_job_builder import PrintJobBuilder
from src.services.storage_service import load_selected_printer, save_selected_printer
from src.utils.response import success_response, error_response


def _resolve_char_width(printer_name, settings):
    """Resolve the character width to use, honoring per-request settings.

    Priority:
      1. settings.char_width        -> explicit character columns (e.g. 32 / 48)
      2. settings.paper_size (mm)   -> 48 cols for >= 80mm, otherwise 32
      3. printer DevMode            -> queried from the printer itself
    """
    settings = settings or {}

    if settings.get('char_width'):
        return int(settings['char_width'])

    paper_size = settings.get('paper_size') or settings.get('paper_size_mm')
    if paper_size:
        return 48 if int(paper_size) >= 80 else 32

    return escpos.get_printer_width(printer_name)


def _parse_print_payload(payload):
    """Accept both the legacy (list of items) and the new (object) payloads.

    New shape:
        {
            "printer": "EPSON TM-T20",      # optional, falls back to selected printer
            "type": "RAW" | "PDF",          # optional, defaults to RAW
            "settings": {"paper_size": 80}, # optional (RAW only)
            "content": [ ...items... ],     # the items to print (RAW)
            "data": "<base64 pdf>"          # the PDF buffer (PDF)
        }

    Legacy shape: a bare list of items -> RAW job using the selected printer.
    """
    if isinstance(payload, dict):
        printer_name = payload.get('printer') or payload.get('printer_name')
        job_type = (payload.get('type') or 'RAW').upper()
        settings = payload.get('settings') or {}
        content = payload.get('content') or payload.get('items') or []
        pdf_data = payload.get('data')
    elif isinstance(payload, list):
        printer_name = None
        job_type = 'RAW'
        settings = {}
        content = payload
        pdf_data = None
    else:
        raise ValueError("Invalid payload: expected an object or a list of items")

    if not printer_name:
        printer_name = load_selected_printer()

    return printer_name, job_type, settings, content, pdf_data


def _unknown_printer_error(printer_name):
    """Return an error_response if the printer does not exist, else None.

    Catches typos (e.g. 'AiYin-AS240-BT' vs the real queue 'AiYin_AS240_BT')
    before `lp`/the spooler fails with an opaque OS error.
    """
    available = escpos.list_printers()
    if printer_name not in available:
        return error_response(
            f"Printer '{printer_name}' not found.", data={"available": available}
        )
    return None


def get_printers():
    """List the printers available on this machine."""
    return success_response(data=escpos.list_printers(), message="Printers listed.")


def get_selected_printer():
    """Return the currently selected default printer."""
    return success_response(data=load_selected_printer())


def set_selected_printer(payload):
    """Set the default printer used when a request does not specify one."""
    payload = payload or {}
    printer_name = payload.get('printer') or payload.get('printer_name')
    if not printer_name:
        return error_response("Field 'printer' is required.")

    available = escpos.list_printers()
    if printer_name not in available:
        return error_response(f"Printer '{printer_name}' not found.", data={"available": available})

    save_selected_printer(printer_name)
    return success_response(data=printer_name, message="Selected printer updated.")


def open_drawer(payload=None):
    """Open the cash drawer of the given (or selected) printer."""
    printer_name = None
    if isinstance(payload, dict):
        printer_name = payload.get('printer') or payload.get('printer_name')
    if not printer_name:
        printer_name = load_selected_printer()

    if not printer_name:
        return error_response("No printer selected.")
    unknown = _unknown_printer_error(printer_name)
    if unknown:
        return unknown

    escpos.send_to_printer(printer_name, "\x1B\x70\x00\x19\xFA")  # Open the cash drawer
    return success_response(data={"printer": printer_name}, message="Cash drawer opened.")


def print_job(payload):
    """Render and send a print job to the target printer.

    Routes by job `type`:
      - "RAW" (default): builds an ESC/POS ticket from `content`.
      - "PDF": prints a base64 PDF buffer (`data`) as a document.
    """
    printer_name, job_type, settings, content, pdf_data = _parse_print_payload(payload)

    if not printer_name:
        return error_response("No printer selected.")
    unknown = _unknown_printer_error(printer_name)
    if unknown:
        return unknown

    if job_type == 'PDF':
        return _print_pdf_job(printer_name, pdf_data, settings)
    if job_type == 'RAW':
        return _print_raw_job(printer_name, settings, content)
    return error_response(f"Unsupported job type '{job_type}'. Use 'RAW' or 'PDF'.")


def _truthy(value):
    """Coerce a setting value (bool / str / number) to a boolean."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'si', 'sí')


def _should_cut(settings, is_label=False):
    """Whether to append a paper cut after a rasterized (raw) PDF job.

    Honors `settings.cut` when provided; when omitted, receipts cut by default
    and labels do not (a mid-label cut would ruin the media).
    """
    cut = settings.get('cut')
    if cut is None:
        return not is_label
    return _truthy(cut)


def _pdf_width_dots(settings):
    """Raster width in dots for PDF rasterization.

    Priority:
      1. settings.width_dots  -> explicit dots/line. Needed for 180-DPI heads
         like the BIXOLON SRP-330II, whose max is 512 dots (not 576). Sending
         576 to such a printer makes it drop the WHOLE raster -> blank ticket.
      2. char_width           -> 576 for >= 48 cols, else 384.
      3. paper_size (mm)      -> 576 for >= 80mm, else 384.
      4. default              -> 576 (80mm @ 203 DPI).
    """
    settings = settings or {}
    if settings.get('width_dots'):
        return int(settings['width_dots'])
    char_width = settings.get('char_width')
    if char_width:
        return 576 if int(char_width) >= 48 else 384
    paper_size = settings.get('paper_size') or settings.get('paper_size_mm')
    if paper_size:
        return 576 if int(paper_size) >= 80 else 384
    return 576  # default to 80mm


def _print_pdf_job(printer_name, pdf_data, settings=None):
    """Decode a base64 PDF buffer and print it.

    Strategy depends on the platform:
      - native PDF (CUPS / macOS / Linux): send the PDF as a document.
      - otherwise (Windows): rasterize the PDF to an ESC/POS image and send raw.
    """
    if not pdf_data:
        return error_response("No PDF data provided. Send the PDF as base64 in 'data'.")

    # Tolerate a data URI prefix (e.g. "data:application/pdf;base64,....").
    if isinstance(pdf_data, str) and ',' in pdf_data and pdf_data.strip().startswith('data:'):
        pdf_data = pdf_data.split(',', 1)[1]

    try:
        pdf_bytes = base64.b64decode(pdf_data)
    except Exception:
        return error_response("Invalid base64 PDF data.")

    if not pdf_bytes.startswith(b'%PDF'):
        return error_response("Provided data is not a valid PDF.")

    return _print_pdf_bytes(printer_name, pdf_bytes, settings)


DOTS_PER_MM = 8  # 203 DPI thermal heads


def _parse_label_size(raw):
    """Normalize label_settings ({width, height, unit}) to mm/dots, or None.

    Raises ValueError with a user-facing message on invalid input.
    """
    if not raw:
        return None

    unit = str(raw.get('unit') or 'mm').lower()
    if unit in ('in', 'inch', 'inches', '"'):
        to_mm = 25.4
    elif unit == 'mm':
        to_mm = 1.0
    else:
        raise ValueError(f"Unsupported unit '{unit}'. Use 'mm' or 'inch'.")

    try:
        width_mm = float(raw['width']) * to_mm
    except (KeyError, TypeError, ValueError):
        raise ValueError("label_settings requires a numeric 'width'.")
    height_mm = None
    if raw.get('height'):
        try:
            height_mm = float(raw['height']) * to_mm
        except (TypeError, ValueError):
            raise ValueError("label_settings 'height' must be a number.")

    return {
        'width_mm': width_mm,
        'height_mm': height_mm,
        'width_dots': int(round(width_mm * DOTS_PER_MM)),
    }


def _print_pdf_bytes(printer_name, pdf_bytes, settings=None):
    """Print raw PDF bytes in one of two modes (settings.pdf_mode):

      - "driver": hand the PDF to the OS print system so the printer's own
        driver renders it. When settings.label_settings gives a size, it is
        passed as custom media (e.g. media=Custom.60x30mm). This is the path
        that works for label printers with a vendor driver (e.g. AiYin),
        whose firmware ignores generic raw jobs.
      - "raw": rasterize the PDF to an ESC/POS image and send it raw. For
        thermal receipt printers, or driverless setups.

    Default: "driver" when label_settings is present, "raw" otherwise (the
    historic receipt behavior). "document" and "raster" are accepted as
    aliases of "driver" and "raw" for backwards compatibility.

    In "raw" mode, settings.cut controls whether a full paper cut is appended
    at the end. When omitted it defaults to True for receipts and False for
    labels. In "driver" mode the cut is controlled by the printer driver, so
    this setting has no effect there.
    """
    settings = settings or {}
    try:
        label = _parse_label_size(settings.get('label_settings'))
    except ValueError as e:
        return error_response(str(e))

    mode = str(settings.get('pdf_mode') or ('driver' if label else 'raw')).lower()

    if mode in ('driver', 'document'):
        options = None
        media = None
        if label and label['height_mm']:
            options = {'media_mm': (label['width_mm'], label['height_mm'])}
            media = f"Custom.{label['width_mm']:g}x{label['height_mm']:g}mm"
        escpos.print_pdf(printer_name, pdf_bytes, options)
        return success_response(
            data={
                "printer": printer_name,
                "type": "PDF",
                "strategy": "driver",
                "media": media,
            },
            message="PDF sent to the printer driver.",
        )

    if mode in ('raw', 'raster'):
        width_dots = label['width_dots'] if label else _pdf_width_dots(settings)
        try:
            escpos_data = escpos.pdf_to_escpos(pdf_bytes, width_dots=width_dots)
        except ImportError as e:
            return error_response(str(e))
        cut = _should_cut(settings, is_label=bool(label))
        if cut:
            escpos_data += escpos.feed_and_cut()
        escpos.send_raw(printer_name, escpos_data)
        return success_response(
            data={
                "printer": printer_name,
                "type": "PDF",
                "strategy": "raw",
                "width_dots": width_dots,
                "cut": cut,
            },
            message="PDF print job sent.",
        )

    return error_response(f"Unsupported pdf_mode '{mode}'. Use 'driver' or 'raw'.")


# Size of the bundled label test asset: 2.36in x 1.18in (60mm x 30mm).
DEFAULT_LABEL_SETTINGS = {"width": 2.36, "height": 1.18, "unit": "inch"}


def print_label_test(printer_name=None, mode=None, label_settings=None):
    """Print the bundled label test PDF (price label, 2.36in x 1.18in).

    mode: "driver" (default) or "raw". label_settings may override the size;
    when omitted, the asset's real size is used.
    """
    if not printer_name:
        printer_name = load_selected_printer()
    if not printer_name:
        return error_response("No printer selected.")
    unknown = _unknown_printer_error(printer_name)
    if unknown:
        return unknown

    try:
        with open(TEST_LABEL_PDF, 'rb') as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        return error_response("Label test PDF asset not found.")

    label_settings = label_settings or {}
    if not label_settings.get('width'):
        label_settings = {**DEFAULT_LABEL_SETTINGS, **label_settings}

    return _print_pdf_bytes(printer_name, pdf_bytes, {
        "label_settings": label_settings,
        "pdf_mode": mode or 'driver',
    })


def print_test(printer_name=None):
    """Print the bundled test PDF asset (80mm @ 300 DPI ticket)."""
    if not printer_name:
        printer_name = load_selected_printer()
    if not printer_name:
        return error_response("No printer selected.")
    unknown = _unknown_printer_error(printer_name)
    if unknown:
        return unknown

    try:
        with open(TEST_PDF, 'rb') as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        return error_response("Test PDF asset not found.")

    return _print_pdf_bytes(printer_name, pdf_bytes, {"paper_size": 80})


def _print_raw_job(printer_name, settings, content):
    """Build an ESC/POS ticket from `content` and send it as a single job."""
    if not content:
        return error_response("No content to print.")

    width = _resolve_char_width(printer_name, settings)
    builder = PrintJobBuilder(width)
    open_withdrawer = False

    for item in content:
        item_type = item.get('type')

        if item_type == 'image' and item.get('data'):
            image_bw = escpos.image_base64_to_bitmap(item['data'])
            if not image_bw:
                return error_response("Error converting image to black and white.")
            resized_image = escpos.resize_image(image_bw, target_width=int(384 * 1))
            image_data = escpos.convert_image_to_escpos_format(resized_image)
            builder.add_image(image_data)

        elif item_type == 'text':
            builder.add_text(
                item['data'],
                align=item.get('align', 'left'),
                font_size=item.get('font_size', 'normal'),
                high_contrast=_truthy(item.get('high_contrast')),
                font_weight=item.get('font_weight', 'normal'),
                font=item.get('font', 'a'),
            )

        elif item_type == 'special_text':
            special_text_data = item['data']
            builder.add_special_text(
                special_text_data['text1'],
                special_text_data['text2'],
                high_contrast=_truthy(item.get('high_contrast')),
                font_weight=item.get('font_weight', 'normal'),
                font=item.get('font', 'a'),
                font_size=item.get('font_size', 'normal'),
            )

        elif item_type == 'table':
            builder.add_table(item['data'].get('rows', []))

        elif item_type == 'separator':
            builder.add_separator()

        elif item_type == 'open_withdrawer':
            open_withdrawer = True

    # Advance the paper and cut.
    builder.add_feed_and_cut()
    if open_withdrawer:
        builder.add_open_drawer()

    # Send the whole ticket as a SINGLE raw job.
    escpos.send_raw(printer_name, builder.to_bytes())

    return success_response(
        data={"printer": printer_name, "char_width": width},
        message="Print job completed.",
    )
