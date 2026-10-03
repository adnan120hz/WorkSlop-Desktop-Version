from PySide6.QtCore import QCoreApplication, Qt
from packaging.version import Version, InvalidVersion
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QDialog, QLabel, QHBoxLayout,
)

from src.gui.ios.components import (
    IOSCollapsibleSection, IOSCard, IOSSettingsRow,
    IOSSwitch, TextInputDialog, NumberInputDialog, decimals_for_step
)
from src.gui.ios.compat import is_tweak_compatible, tweak_incompatibility_reason
from src.devicemanagement.constants import mobilegestalt_decision
from src.tweaks.capabilities import (
    clear_audit_research_only_state, clear_unsupported_mobilegestalt_state,
)
from src.gui.theme import ColorThemeManager
from src.tweaks.tweaks import tweaks, TweakID, set_tweak_enabled
from src.tweaks.registry import SPECS_BY_SECTION, SPECS_BY_ID, SECTION_FEATURES, Kind, Section
from src.tweaks.tweak_loader import load_plist_tweaks, load_eligibility
from src.tweaks.hidden import current_hidden_feature_names, current_hidden_tweak_names
from src.gui.ios.eligibility import EligibilitySection
from src.gui.ios.risky import RiskySection

# Feature (page) name -> registry Section it maps to in the iOS tweaks UI.
# A HotLoad-hidden feature loses its whole section here (and the Sidebar/Home
# entries), so its tweaks are never even shown.
_SECTION_FEATURES = SECTION_FEATURES


def _hidden_feature_names() -> set:
    """Names of HotLoad-hidden features for the current setup, as a set."""
    return current_hidden_feature_names()


def _fmt_number(value) -> str:
    """Render a numeric tweak value compactly (5, 0.5, 1)."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _lock_reason(tweak_id: TweakID, device_version: str = "",
                 is_iphone: bool = True, device_build: str = "") -> str:
    """Why this tweak's control is locked on the current device.

    Returns "" when the tweak is supported (control stays enabled).
    User decision 2026-10-01: unsupported tweaks stay visible but locked
    instead of being hidden or toggleable. The reason comes from the same
    deliverability predicate the backend uses, so a MobileGestalt-backed
    tweak shows the shared capability reason, not a generic version guess.
    """
    reason = tweak_incompatibility_reason(
        tweak_id, device_version, is_iphone, device_build)
    if reason:
        return (QCoreApplication.translate("Nugget", "Locked: ") + reason)
    spec = SPECS_BY_ID.get(tweak_id)
    if spec is None:
        return ""
    bits = []
    if spec.min_version:
        bits.append(QCoreApplication.translate(
            "Nugget", "Requires iOS %1 or later").replace("%1", spec.min_version))
    if spec.max_version:
        bits.append(QCoreApplication.translate(
            "Nugget", "Requires iOS %1 or earlier").replace("%1", spec.max_version))
    if spec.iphone_only:
        bits.append(QCoreApplication.translate("Nugget", "iPhone only"))
    if spec.ipad_only:
        bits.append(QCoreApplication.translate("Nugget", "iPad only"))
    if not bits:
        return ""
    return (QCoreApplication.translate("Nugget", "Locked: ")
            + "; ".join(bits))


def _hidden_tweak_names() -> set:
    """Names of the tweaks that belong to HotLoad-hidden features for the
    current setup. Used by the preset loader to strip them during load."""
    return current_hidden_tweak_names()


def _hidden_sections() -> set:
    """Registry Sections whose feature is hidden, so we skip rendering them."""
    hidden = _hidden_feature_names()
    return {s for s, feat in _SECTION_FEATURES.items() if feat in hidden}


# Collapsed tweak sections are remembered per section name, so a rebuild (or a
# restart) comes back exactly as the user left it.
_COLLAPSED_KEY = "tweaks_collapsed_sections"


def _load_collapsed_sections() -> set:
    """Section names the user collapsed."""
    from src.controllers.settings import Settings
    raw = Settings("settings").value(_COLLAPSED_KEY, "", type=str) or ""
    return {part.strip() for part in str(raw).split(",") if part.strip()}


def _save_collapsed_section(name: str, collapsed: bool):
    from src.controllers.settings import Settings
    store = Settings("settings")
    names = _load_collapsed_sections()
    if collapsed:
        names.add(name)
    else:
        names.discard(name)
    store.setValue(_COLLAPSED_KEY, ",".join(sorted(names)))


# Layout rhythm for the tweaks page: one set of numbers for the
# whole page so every section and every tweak row lines up. The row-card
# constants are also used by eligibility.py / risky.py, which render their
# rows inside this page's collapsible sections (imported lazily there to
# avoid a circular import: this module imports those at top level).
ROW_CARD_MIN_HEIGHT = 56  # every tweak row card gets the same minimum height
ROW_CARD_HMARGIN = 16     # horizontal padding inside a card
ROW_CARD_VMARGIN = 10     # vertical padding inside a card
SWITCH_COL_WIDTH = 64     # fixed right column: all switches on one vertical line
ROW_LABEL_FONT_PX = 15

_PAGE_MARGIN = 16      # outer page margins
_SECTION_GAP = 16      # vertical gap between collapsible sections
_ROW_GAP = 8           # vertical gap between tweak cards inside a section


def make_switch_column(card, switch):
    """Fixed-width right column holding a fixed-size switch.

    ``IOSSwitch`` is already a fixed 51x31 painted widget (no stretch, no
    rotation); the 64px column pins it to the same vertical line on every
    row regardless of label length.
    """
    col = QWidget(card)
    col.setFixedWidth(SWITCH_COL_WIDTH)
    col_layout = QHBoxLayout(col)
    col_layout.setContentsMargins(0, 0, 0, 0)
    col_layout.setSpacing(0)
    col_layout.addStretch(1)
    col_layout.addWidget(switch, 0, Qt.AlignVCenter | Qt.AlignRight)
    return col


class IOSSectionContent(QWidget):
    """iOS-style tweak controls for one or more registry sections.

    Can be reused inside any scroll area or page.
    """

    def __init__(self, window, sections=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.sections = sections
        self._switch_labels = []
        self._solarium_visible: bool = None

        # Load tweaks (idempotent) so the sections below actually populate
        load_plist_tweaks()

        # persistent root layout: keeps only a rebuildable inner widget
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._inner = None

        self.rebuild()

    def rebuild(self):
        """(Re)build the section controls for the currently selected device.

        Called once in ``__init__`` and again whenever the selected device
        changes, so per-device compatibility filtering (``min_version`` /
        ``iphone_only`` / ``ipad_only`` from the registry) and HotLoad-hiding
        are re-evaluated instead of being frozen at startup, when no device is
        known yet (that would wrongly hide e.g. the Dynamic Island tweaks).
        """
        # Tear down the previous build (widgets + layout) so the section can be
        # re-rendered in place from the single registry definition below.
        if self._inner is not None:
            self.layout().removeWidget(self._inner)
            self._inner.deleteLater()
            self._inner = None

        layout = QVBoxLayout()
        layout.setContentsMargins(_PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN, 32)
        layout.setSpacing(_SECTION_GAP)
        inner = QWidget(self)
        inner.setLayout(layout)
        self._inner = inner
        self.layout().addWidget(inner)

        self._switch_labels = []
        self._switches = {}
        self.force_solarium_fallback_card = None

        try:
            device_ver = self.window.device_manager.get_current_device_version()
        except Exception:
            device_ver = ""
        try:
            device_build = self.window.device_manager.get_current_device_build()
        except Exception:
            device_build = ""
        # Wave 10: a device switch is a state transition, not just a repaint.
        # If MobileGestalt is locked/unknown on the newly selected device,
        # stale ON state from a supported device, a preset, or the no-device
        # screen is forced off before anything renders or counts it.
        clear_unsupported_mobilegestalt_state(
            mobilegestalt_decision(device_build, device_ver), tweaks_dict=tweaks)
        # Wave 11 (user order 2026-10-03): the audit research-only
        # classification no longer locks or clears rows; this call is a
        # no-op kept so the rebuild path and the backend share one shape.
        # MobileGestalt clearing above is the only force-off left.
        clear_audit_research_only_state(device_ver, device_build, tweaks_dict=tweaks)
        # iOS 27 moved the feature-flag store from
        # /var/preferences/FeatureFlags/Global.plist to
        # /var/preferences/FeatureFlags/Settings.plist (sole path read by the
        # framework; no fallback), and no working delivery channel is publicly
        # confirmed on iOS 27 — so the Feature Flags section is experimental
        # there. iOS 26 and lower keep the old, working behavior unchanged.
        try:
            is_ios27 = bool(device_ver) and Version(device_ver) >= Version("27.0")
        except InvalidVersion:
            is_ios27 = False
        try:
            model = self.window.device_manager.get_current_device_model() or ""
        except Exception:
            model = ""
        is_iphone = model.startswith("iPhone")
        self._device_version = device_ver
        self._device_build = device_build
        self._is_iphone = is_iphone

        def is_compatible(tweak_id: TweakID) -> bool:
            return is_tweak_compatible(tweak_id, device_ver, is_iphone, device_build)

        # Helper to create a switch row for boolean tweaks.
        # Every row is the same height with the same inner padding, and the
        # switch lives in a fixed-width right column so all switches line up
        # on one vertical line no matter how long the label is.
        def make_switch(tweak_id: TweakID, title: str, description: str = "",
                        target: QVBoxLayout = None):
            if tweak_id not in tweaks:
                return
            tweak = tweaks[tweak_id]
            card = IOSCard()
            card.setMinimumHeight(ROW_CARD_MIN_HEIGHT)
            if tweak_id == TweakID.ForceSolariumFallback:
                self.force_solarium_fallback_card = card
            # Unsupported on this iOS: visible but locked (user decision
            # 2026-10-01) instead of hidden — the switch cannot be toggled.
            lock_reason = "" if is_compatible(tweak_id) else _lock_reason(tweak_id, device_ver, is_iphone, device_build)
            if lock_reason:
                card.setEnabled(False)
            row_layout = QHBoxLayout(card)
            row_layout.setContentsMargins(
                ROW_CARD_HMARGIN, ROW_CARD_VMARGIN, ROW_CARD_HMARGIN, ROW_CARD_VMARGIN)
            row_layout.setSpacing(12)

            c = ColorThemeManager.instance().colors
            label = QLabel(title)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color: {c.text_primary}; font-size: {ROW_LABEL_FONT_PX}px;"
                " background-color: transparent;")
            self._switch_labels.append(label)
            # Wave 11 (user order 2026-10-03): no UNPROVEN / device-test
            # badge or extra tooltip warning on any row. Tweaks that passed
            # the structure audit are normal tweaks; the Wave 10 badge was
            # the visible half of the "untested Liquid Glass" complaint.
            row_layout.addWidget(label, 1)

            switch = IOSSwitch(tweak.enabled)
            self._switches[tweak_id] = switch
            switch.toggled.connect(
                lambda checked, tid=tweak_id: self._on_registry_switch(tid, checked))
            row_layout.addWidget(make_switch_column(card, switch))

            tip = description
            if lock_reason:
                tip = (tip + "\n\n" + lock_reason) if tip else lock_reason
            if tip:
                label.setToolTip(tip)
                switch.setToolTip(tip)
                card.setToolTip(tip)

            (target or layout).addWidget(card)

        # Helper for text input tweaks: same card shell as the switch rows so
        # every row on the page has identical height and padding.
        def make_text_input(tweak_id: TweakID, title: str, description: str = "",
                            target: QVBoxLayout = None):
            if tweak_id not in tweaks:
                return
            # Unsupported on this iOS: visible but locked (user decision
            # 2026-10-01) instead of skipped — the dialog cannot be opened.
            lock_reason = "" if is_compatible(tweak_id) else _lock_reason(tweak_id, device_ver, is_iphone, device_build)
            tweak = tweaks[tweak_id]
            card = IOSCard()
            card.setMinimumHeight(ROW_CARD_MIN_HEIGHT)
            if lock_reason:
                card.setEnabled(False)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(
                ROW_CARD_HMARGIN, ROW_CARD_VMARGIN, ROW_CARD_HMARGIN, ROW_CARD_VMARGIN)
            card_layout.setSpacing(0)
            row = IOSSettingsRow(title)
            row.setMinimumHeight(ROW_CARD_MIN_HEIGHT - 2 * ROW_CARD_VMARGIN)
            tip = description
            if lock_reason:
                tip = (tip + "\n\n" + lock_reason) if tip else lock_reason
            if tip:
                row.setToolTip(tip)
            current = ""
            if hasattr(tweak, 'value') and tweak.value:
                current = str(tweak.value)
                row.setText(f"{title}  ({current})")
            row.clicked.connect(lambda: self._show_text_input_dialog(tweak_id, title, current, row))
            card_layout.addWidget(row)
            (target or layout).addWidget(card)

        # Helper for number input tweaks: same card shell as the other rows.
        def make_number_input(tweak_id: TweakID, title: str, min_val: int = 0, max_val: int = 999,
                              description: str = "", step: float = 1.0,
                              target: QVBoxLayout = None):
            if tweak_id not in tweaks:
                return
            # Unsupported on this iOS: visible but locked (user decision
            # 2026-10-01) instead of skipped — the dialog cannot be opened.
            lock_reason = "" if is_compatible(tweak_id) else _lock_reason(tweak_id, device_ver, is_iphone, device_build)
            tweak = tweaks[tweak_id]
            card = IOSCard()
            card.setMinimumHeight(ROW_CARD_MIN_HEIGHT)
            if lock_reason:
                card.setEnabled(False)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(
                ROW_CARD_HMARGIN, ROW_CARD_VMARGIN, ROW_CARD_HMARGIN, ROW_CARD_VMARGIN)
            card_layout.setSpacing(0)
            row = IOSSettingsRow(title)
            row.setMinimumHeight(ROW_CARD_MIN_HEIGHT - 2 * ROW_CARD_VMARGIN)
            tip = description
            if tip:
                tip = (tip + "\n\n"
                       + QCoreApplication.translate("Nugget", "Range: {0} – {1}")
                       .format(_fmt_number(min_val), _fmt_number(max_val)))
            if lock_reason:
                tip = (tip + "\n\n" + lock_reason) if tip else lock_reason
            if tip:
                row.setToolTip(tip)
            decimals = decimals_for_step(step)
            current = 0
            if hasattr(tweak, 'value') and tweak.value:
                current = int(tweak.value) if decimals == 0 else float(tweak.value)
                row.setText(f"{title}  ({_fmt_number(current)})")
            row.clicked.connect(lambda: self._show_number_input_dialog(
                tweak_id, title, current, row, min_val, max_val, step))
            card_layout.addWidget(row)
            (target or layout).addWidget(card)

        # Render sections straight from the registry. Titles (and descriptions)
        # are stored as QT_TRANSLATE_NOOP markers and translated here, at
        # render time.
        def tr_title(spec) -> str:
            return QCoreApplication.translate("Nugget", spec.title)

        def tr_description(spec) -> str:
            if not spec.description:
                return ""
            return QCoreApplication.translate("Nugget", spec.description)

        renderers = {
            Kind.SWITCH: lambda spec, target: make_switch(
                spec.id, tr_title(spec), tr_description(spec), target),
            Kind.TEXT: lambda spec, target: make_text_input(
                spec.id, tr_title(spec), tr_description(spec), target),
            Kind.NUMBER: lambda spec, target: make_number_input(
                spec.id, tr_title(spec), spec.min_value, spec.max_value,
                tr_description(spec), spec.step, target),
        }

        sections_to_render = self.sections if self.sections is not None else list(Section)
        hidden_sections = _hidden_sections()
        collapsed_sections = _load_collapsed_sections()
        for section in sections_to_render:
            if section in hidden_sections:
                continue
            if not SPECS_BY_SECTION[section]:
                # Wave 10 Package 1: a section whose audited specs were all
                # killed (Feature Flags) must not render as an empty product
                # section.
                continue
            collapsible = IOSCollapsibleSection(
                QCoreApplication.translate("Nugget", section.value),
                expanded=section.value not in collapsed_sections)
            collapsible.body_layout.setSpacing(_ROW_GAP)
            collapsible.toggled.connect(
                lambda expanded, name=section.value: _save_collapsed_section(
                    name, not expanded))
            layout.addWidget(collapsible)
            # iOS 27 notice, shown ONLY on iOS 27+. Nothing is added on iOS 26
            # and lower, so the stable path renders exactly as before.
            # Rebuilt with the page, so it tracks device changes.
            if section == Section.FEATURE_FLAGS and is_ios27:
                ff_warn = QLabel(QCoreApplication.translate(
                    "Nugget",
                    "Locked on iOS 27: Apple moved the feature-flag "
                    "store to /var/preferences/FeatureFlags/Settings.plist, "
                    "which this section does not write — these switches "
                    "target the iOS 26 location "
                    "(/var/preferences/FeatureFlags/Global.plist) that iOS 27 "
                    "no longer reads, and no working delivery channel is "
                    "known. Fully supported on iOS 26.1 and lower."
                ))
                ff_warn.setWordWrap(True)
                c_warn = ColorThemeManager.instance().colors
                ff_warn.setStyleSheet(
                    f"color: {c_warn.text_secondary}; font-size: 13px;"
                    " background-color: transparent;")
                collapsible.body_layout.addWidget(ff_warn)
            for spec in SPECS_BY_SECTION[section]:
                renderers[spec.kind](spec, collapsible.body_layout)

        # Eligibility section (ported from leminlimez/Nugget's eligibility
        # page: EU Enabler, Apple Intelligence, spoofing). Rendered as a
        # collapsible section like the registry sections above.
        try:
            current_device = self.window.device_manager.data_singleton.current_device
        except Exception:
            current_device = None
        load_eligibility(current_device)
        elig_collapsible = IOSCollapsibleSection(
            QCoreApplication.translate("Nugget", "Eligibility"),
            expanded="Eligibility" not in collapsed_sections)
        elig_collapsible.body_layout.setSpacing(_ROW_GAP)
        elig_collapsible.toggled.connect(
            lambda expanded: _save_collapsed_section("Eligibility", not expanded))
        layout.addWidget(elig_collapsible)
        elig_section = EligibilitySection(self.window)
        elig_collapsible.body_layout.addWidget(elig_section)
        elig_section.refresh()

        # Risky section (ported from leminlimez/Nugget's risky page:
        # Disable OTA Updates, Custom Resolution). Rendered as a
        # collapsible section like Eligibility above.
        risky_collapsible = IOSCollapsibleSection(
            QCoreApplication.translate("Nugget", "Risky"),
            expanded="Risky" not in collapsed_sections)
        risky_collapsible.body_layout.setSpacing(_ROW_GAP)
        risky_collapsible.toggled.connect(
            lambda expanded: _save_collapsed_section("Risky", not expanded))
        layout.addWidget(risky_collapsible)
        risky_section = RiskySection(self.window)
        risky_collapsible.body_layout.addWidget(risky_section)
        risky_section.refresh()

        layout.addStretch()

        # re-apply any remembered solarium-card visibility to the fresh card
        if self._solarium_visible is not None and self.force_solarium_fallback_card is not None:
            self.force_solarium_fallback_card.setVisible(self._solarium_visible)

    def _current_compatible(self, tweak_id: TweakID) -> bool:
        """Re-check deliverability at mutation time (not just render time)."""
        try:
            dm = self.window.device_manager
            version = dm.get_current_device_version() or ""
            build = dm.get_current_device_build() or ""
            model = dm.get_current_device_model() or ""
        except Exception:
            version = getattr(self, "_device_version", "") or ""
            build = getattr(self, "_device_build", "") or ""
            model = "iPhone" if getattr(self, "_is_iphone", True) else ""
        return is_tweak_compatible(
            tweak_id, version, model.startswith("iPhone"), build)

    def _on_registry_switch(self, tweak_id: TweakID, checked: bool):
        # State-level guard: a visible-but-locked card cannot be toggled, but
        # programmatic signals, stale switches, and preset-synced widgets can
        # still fire. Re-check the shared predicate before mutating the model;
        # an unsupported tweak is forced off instead of enabled.
        if checked and not self._current_compatible(tweak_id):
            set_tweak_enabled(tweak_id, False)
            sw = self._switches.get(tweak_id)
            if sw is not None and sw.isChecked():
                sw.blockSignals(True)
                sw.setChecked(False)
                sw.blockSignals(False)
            return
        # Wave 11 (user order 2026-10-03): enabling a normal tweak never
        # opens a confirmation dialog. The Wave 10 device-test confirmation
        # lived here and named Liquid Glass in its text while firing for
        # research-only rows in ANY section, which is exactly the reported
        # "I enabled another tweak and got an untested Liquid Glass
        # notification" bug. The dialog and its call are deleted, not
        # reworded: no tweak reaches a device-test state any more.
        # Mutual exclusion (B26): enabling one side of an Enable/Disable or
        # RTL/LTR pair turns the other side off in the model; keep the partner
        # switches visually in sync without re-firing their toggled signals.
        set_tweak_enabled(tweak_id, checked)
        spec = SPECS_BY_ID.get(tweak_id)
        if spec is None:
            return
        for other_id in spec.excludes:
            sw = self._switches.get(other_id)
            if sw is not None and sw.isChecked():
                sw.blockSignals(True)
                sw.setChecked(False)
                sw.blockSignals(False)

    def set_force_solarium_fallback_visible(self, visible: bool):
        # remember the intended state so a rebuild re-applies it (the card
        # pointer is recreated by rebuild())
        self._solarium_visible = visible
        if self.force_solarium_fallback_card is not None:
            self.force_solarium_fallback_card.setVisible(visible)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        for lbl in self._switch_labels:
            lbl.setStyleSheet(
                f"color: {c.text_primary}; font-size: {ROW_LABEL_FONT_PX}px;"
                " background-color: transparent;")

    def _show_text_input_dialog(self, tweak_id: TweakID, title: str, current: str, row: IOSSettingsRow):
        if not self._current_compatible(tweak_id):
            set_tweak_enabled(tweak_id, False)
            return
        dialog = TextInputDialog(title, current, self)
        if dialog.exec() == QDialog.Accepted:
            value = dialog.get_value()
            tweaks[tweak_id].set_value(value, toggle_enabled=True)
            display = value if value else "(empty)"
            row.setText(f"{title}  ({display})")

    def _show_number_input_dialog(self, tweak_id: TweakID, title: str, current, row: IOSSettingsRow, min_val, max_val, step: float = 1.0):
        if not self._current_compatible(tweak_id):
            set_tweak_enabled(tweak_id, False)
            return
        dialog = NumberInputDialog(title, current, min_val, max_val, self, step=step)
        if dialog.exec() == QDialog.Accepted:
            value = dialog.get_value()
            tweaks[tweak_id].set_value(value, toggle_enabled=True)
            row.setText(f"{title}  ({_fmt_number(value)})")


class IOSTweaksPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        self.content = IOSSectionContent(window, list(Section), self)
        scroll.setWidget(self.content)
        layout.addWidget(scroll)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._scroll.setStyleSheet(f"background-color: {c.bg_primary}; border: none;")
        self.content._retheme()

    def set_force_solarium_fallback_visible(self, visible: bool):
        self.content.set_force_solarium_fallback_visible(visible)

    def rebuild(self):
        self.content.rebuild()


class IOSSectionPage(QWidget):
    """Standalone iOS-style page for a single tweak section."""

    def __init__(self, window, section: Section, parent=None):
        super().__init__(parent)
        self.window = window
        self.section = section
        self.setObjectName("iosContainer")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        self.content = IOSSectionContent(window, [section], self)
        scroll.setWidget(self.content)
        layout.addWidget(scroll)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._scroll.setStyleSheet(f"background-color: {c.bg_primary}; border: none;")
        self.content._retheme()

    def set_force_solarium_fallback_visible(self, visible: bool):
        self.content.set_force_solarium_fallback_visible(visible)

    def rebuild(self):
        self.content.rebuild()
