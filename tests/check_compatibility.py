#!/usr/bin/env python3
"""Offline, source-derived checks for the patch's existing 1.15 integrations.

Run with --game, --ir and --mr pointing at the supplied source directories.
This deliberately extracts only tokens and named blocks, not game semantics.
"""

import argparse
import re
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path


MOD = Path(__file__).resolve().parents[1] / "mod"
LEXEME = re.compile(
    r'\s+|\#[^\n]*|"(?:\\.|[^"\\])*"|[{}]|[<>!?]?=|[<>]|[^\s{}=<>!?#"]+',
)
LANGUAGES = (
    "braz_por", "english", "french", "german", "japanese", "korean",
    "polish", "russian", "simp_chinese", "spanish", "turkish",
)
AIRCRAFT_TT = "curtiss_has_aeroplane_production_size_x_tooltip_trigger_tt"
MILITARY_TT = "MR_ACADEMICS_MILITARY_BUILDING_REQUIREMENT_2_TT"
OBSOLETE_TT = "MR_CURTISS_FOUND_PILOT_SCHOOL_BUTTON_TRIGGER_TT"


def tokens(text: str) -> list[str]:
    """Ignore comments/BOM and normalize numeric spelling, never quoted content."""
    result = []
    position = 0
    text = text.removeprefix("\ufeff")
    for match in LEXEME.finditer(text):
        if match.start() != position:
            raise ValueError(
                f"unrecognized token near {text[position:position + 40]!r}",
            )
        position = match.end()
        value = match.group()
        if value.isspace() or value.startswith("#"):
            continue
        if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            value = format(Decimal(value).normalize(), "f")
        result.append(value)
    if position != len(text):
        raise ValueError(f"unterminated string near {text[position:position + 40]!r}")
    return result


def blocks(items: list[str]) -> list[tuple[str, list[str]]]:
    """Extract direct named blocks, keeping nested tokens and duplicate keys."""
    found = []
    depth = 0
    start = 0
    for index, item in enumerate(items):
        if item == "{":
            if depth == 0:
                if index < 2 or items[index - 1] != "=":
                    raise ValueError("unnamed block")
                start = index
            depth += 1
        elif item == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("unmatched closing brace")
            if depth == 0:
                found.append((items[start - 2], items[start + 1:index]))
    if depth:
        raise ValueError("unclosed block")
    return found


def one_block(items: list[str], name: str) -> list[str]:
    """Require exactly one direct definition; missing data must fail, not skip."""
    matches = [body for key, body in blocks(items) if key == name]
    if len(matches) != 1:
        raise ValueError(f"{name}: expected one block, found {len(matches)}")
    return matches[0]


def source(path: Path, name: str) -> list[str]:
    """Read one exact source symbol without writing caches or upstream files."""
    try:
        return one_block(tokens(path.read_text(encoding="utf-8-sig")), name)
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError(f"{path} / {name}: {error}") from error


def rewrite(items: list[str], old: str, new: str, count: int) -> list[str]:
    """Apply a bounded compatibility delta to independently read upstream tokens."""
    before, after = tokens(old), tokens(new)
    result = []
    index = hits = 0
    while index < len(items):
        if items[index:index + len(before)] == before:
            result.extend(after)
            index += len(before)
            hits += 1
        else:
            result.append(items[index])
            index += 1
    if hits != count:
        raise ValueError(f"source delta {old!r}: expected {count} matches, got {hits}")
    return result


def equal(actual: list[str], expected: list[str]) -> None:
    """Report the first differing token with enough context to locate the field."""
    if actual == expected:
        return
    index = next(
        (i for i, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]),
        min(len(actual), len(expected)),
    )
    raise AssertionError(
        f"token {index}: expected {' '.join(expected[max(0, index - 3):index + 9])!r}; "
        f"got {' '.join(actual[max(0, index - 3):index + 9])!r}",
    )


def contains(items: list[str], required: str) -> None:
    """Require a literal contract independently of source-derived comparisons."""
    needle = tokens(required)
    if not any(items[i:i + len(needle)] == needle for i in range(len(items))):
        raise AssertionError(f"missing required predicate {required}")


def locale_value(text: str, key: str) -> str:
    """Extract a quoted localization value without treating markup # as comments."""
    matches = re.findall(
        rf'^\s*{re.escape(key)}:\d*\s*("(?:\\.|[^"\\])*")', text, re.MULTILINE,
    )
    if len(matches) != 1:
        raise ValueError(f"{key}: expected one localization, got {len(matches)}")
    return matches[0]


def self_checks() -> None:
    """Catch scanner regressions before trusting source comparisons."""
    sample = '\ufeffa={ text="braces { } # \\"quoted\\"" # } fake={}\n n>=0.50 n=10 }'
    equal(
        one_block(tokens(sample), "a"),
        ["text", "=", '"braces { } # \\"quoted\\""', "n", ">=", "0.5", "n", "=", "10"],
    )
    for invalid in ("a={", "a={}}", 'a={x="unfinished}', "a={} a={}"):
        try:
            one_block(tokens(invalid), "a")
        except ValueError:
            continue
        raise AssertionError(f"scanner accepted invalid definition: {invalid}")
    text = b'\xef\xbb\xbfl_english:\n key:0 "#default_text { \\"x\\" }#!" # note'
    if locale_value(text.decode("utf-8-sig"), "key") != '"#default_text { \\"x\\" }#!"':
        raise AssertionError("BOM/quoted localization self-check failed")


def check_loader(patch: Path, upstream: Path) -> None:
    """Check additive filenames/load order and the two distinct override syntaxes."""
    if patch.name == upstream.name:
        raise AssertionError("full-file shadows are forbidden")
    if patch.suffix != ".txt" or patch.name <= upstream.name:
        raise AssertionError(f"filename must load after {upstream.name}")
    definitions = blocks(tokens(patch.read_text(encoding="utf-8-sig")))
    if patch.parent == MOD / "events":
        if any(":" in name for name, _ in definitions):
            raise AssertionError("root events require bare IDs, not REPLACE:")
    elif patch.is_relative_to(MOD / "common"):
        if any(not name.startswith("REPLACE:") for name, _ in definitions):
            raise AssertionError("existing common database overrides require REPLACE:")
    else:
        raise AssertionError("events must be in the patch's root events directory")


def check_electrics(game: Path, ir: Path, mr: Path) -> None:
    """Keep IR's fields and game's copper extension, adding only MR's injections."""
    name = "company_basic_electrics"
    actual = source(
        MOD / "common/company_types/zzzzirmr_vanilla_company_types.txt",
        "REPLACE:" + name,
    )
    expected = source(ir / "common/company_types/zir_companies.txt", "REPLACE:" + name)
    injection = source(
        mr / "common/company_types/vanilla_company_types.txt", "TRY_INJECT:" + name,
    )
    vanilla = source(game / "common/company_types/99_basic_companies.txt", name)
    equal(
        one_block(expected, "extension_building_types"),
        one_block(vanilla, "extension_building_types"),
    )
    # These top-level fields have different source ordering, unlike their contents.
    for field, extra in blocks(injection):
        original = one_block(expected, field)
        expected = rewrite(
            expected, f"{field} = {{ {' '.join(original)} }}",
            f"{field} = {{ {' '.join(original + extra)} }}", 1,
        )
    equal(
        one_block(actual, "extension_building_types"),
        one_block(expected, "extension_building_types"),
    )
    industries = (
        "building_types = { building_electrics_industry building_radio_industry }"
    )
    equal(rewrite(actual, industries, "", 1), rewrite(expected, industries, "", 1))


def compare_company(actual: list[str], expected: list[str]) -> None:
    """Extension fields moved in the old patch; their ordering is not gameplay."""
    equal(
        one_block(actual, "extension_building_types"),
        one_block(expected, "extension_building_types"),
    )
    field = "extension_building_types = { building_aircraft_industry }"
    equal(rewrite(actual, field, "", 1), rewrite(expected, field, "", 1))


def military_delta(items: list[str]) -> list[str]:
    """Replace cars with a single level-five tank OR aircraft plant."""
    return rewrite(
        items, "AND = { is_building_type = building_automotive_industry level >= 5 }",
        "AND = { is_building_type = building_war_machine_industry level >= 5 } "
        "AND = { is_building_type = building_aircraft_industry level >= 5 }", 1,
    )


def aviation_delta(items: list[str]) -> list[str]:
    """Translate MR's automotive/PM predicates to IR's dedicated aircraft building."""
    pairs = (
        (
            "is_production_method_active = { "
            "building_type = building_automotive_industry "
            "production_method = pm_aeroplane_production }",
            "has_building = building_aircraft_industry",
        ),
        ("has_active_production_method = pm_aeroplane_production", ""),
        ("building_automotive_industry", "building_aircraft_industry"),
        ('"building_automotive_industry"', '"building_aircraft_industry"'),
        (
            "building_automotive_industry_throughput_add",
            "building_aircraft_industry_throughput_add",
        ),
    )
    for old, new in pairs:
        before = tokens(old)
        count = sum(items[i:i + len(before)] == before for i in range(len(items)))
        if count:
            items = rewrite(items, old, new, count)
    return items


def check_locale(language: str, mr: Path) -> None:
    """Preserve translations and the single-building requirement."""
    path = MOD / f"localization/{language}/zzirmr_{language}.yml"
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    if not data.startswith(b"\xef\xbb\xbf") or not text.startswith(f"l_{language}:\n"):
        raise AssertionError("expected UTF-8 BOM and matching language header")
    if not path.name.endswith(f"_{language}.yml"):
        raise AssertionError("localization filename must end in its language suffix")
    upstream = mr / f"localization/{language}"
    aircraft = locale_value(
        (upstream / f"curtiss_l_{language}.yml").read_text(encoding="utf-8-sig"),
        AIRCRAFT_TT,
    )
    aircraft = aircraft.replace(
        "building_automotive_industry", "building_aircraft_industry",
    )
    if language == "korean":
        # Upstream says national total; this predicate requires one qualifying building.
        aircraft = aircraft.replace("의 #V 건물 단계가 총 ", "의 #V 건물 단계가 ")
    if locale_value(text, AIRCRAFT_TT) != aircraft:
        raise AssertionError(
            f"{AIRCRAFT_TT}: expected current MR translation "
            "with aircraft substitution and single-building scope",
        )
    military = locale_value(
        (upstream / f"mr_GUI_l_{language}.yml").read_text(encoding="utf-8-sig"),
        MILITARY_TT,
    )
    # MR still has English fallbacks here; keep these existing patch translations.
    translations = {
        "braz_por": ("tem pelo menos um", "ou", "do nível", "ou superior"),
        "french": ("a au moins un", "ou", "du niveau", "ou supérieur"),
        "spanish": ("tiene al menos un", "o", "del nivel", "o superior"),
    }
    if language in translations:
        has, conjunction, level, higher = translations[language]
        military = military.replace("has at least one", has)
        military = military.replace(" or ", f" {conjunction} ")
        military = military.replace("of level", level)
        military = military.replace(f"{conjunction} higher", higher)
    separator = "、" if language == "simp_chinese" else ", "
    if language == "korean":
        military = military.replace(
            "[GetBuildingType('building_automotive_industry').GetName]이나",
            "[GetBuildingType('building_war_machine_industry').GetName], "
            "[GetBuildingType('building_aircraft_industry').GetName]이나",
        )
    else:
        military = military.replace(
            "[GetBuildingType('building_automotive_industry').GetName]",
            "[GetBuildingType('building_war_machine_industry').GetName]" + separator
            + "[GetBuildingType('building_aircraft_industry').GetName]",
        )
    if locale_value(text, MILITARY_TT) != military:
        raise AssertionError(
            f"{MILITARY_TT}: expected five industries and current translation",
        )


def main() -> int:
    """Accumulate file/symbol diagnostics and return the CLI status."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("game", "ir", "mr"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    failures = []
    passed = 0

    def check(label: str, action: Callable[[], None]) -> None:
        nonlocal passed
        try:
            action()
        except (AssertionError, OSError, UnicodeError, ValueError) as error:
            failures.append(f"FAIL {label}: {error}")
        else:
            passed += 1

    check("parser/BOM self-checks", self_checks)
    check(
        "company_basic_electrics / copper extension and preserved IR+MR fields",
        lambda: check_electrics(args.game, args.ir, args.mr),
    )
    cases = [
        (
            "common/scripted_effects/"
            "zzzzirmr_ai_promote_and_tech_school_scripted_effects.txt",
            "common/scripted_effects/"
            "mr_ai_promote_and_tech_school_scripted_effects.txt",
            "ai_choose_tech_school_effect", military_delta,
        ),
        (
            "common/scripted_guis/zzzzirmr_general_focus_sguis.txt",
            "common/scripted_guis/MR_general_focus_sguis.txt",
            "mr_academics_change_to_military_school_sgui", military_delta,
        ),
        (
            "common/character_traits/zzzzirmr_tesla_traits.txt",
            "common/character_traits/mr_science_tesla_traits.txt",
            "tesla_aeronautical_engineer", aviation_delta,
        ),
        (
            "common/decisions/zzzzirmr_sports_curtiss_decisions.txt",
            "common/decisions/mr_sports_curtiss_decisions.txt",
            "curtiss_found_pilot_school_decision", aviation_delta,
        ),
        (
            "common/script_values/zzzzirmr_curtiss_script_values.txt",
            "common/script_values/mr_sports_curtiss_script_value.txt",
            "curtiss_schneider_trophy_before_race_points_score", aviation_delta,
        ),
    ]
    for name in (
        "curtiss_company_basic_air_travel", "curtiss_company_KLM",
        "curtiss_company_DLR",
        "curtiss_company_imperial_airways", "curtiss_company_air_france",
        "curtiss_company_swissair",
    ):
        cases.append((
            "common/company_types/zzzzirmr_curtiss_company_types.txt",
            "common/company_types/mr_curtiss_company_types.txt", name, aviation_delta,
        ))
    for name in (
        "curtiss_water_airport_modifier", "curtiss_thriving_aeroplane_factory_modifier",
        "curtiss_airplane_revolution_modifier", "curtiss_zeppelin_wharf_modifier",
    ):
        cases.append((
            "common/static_modifiers/zzzzirmr_curtiss_modifiers.txt",
            "common/static_modifiers/curtiss_modifiers.txt", name, aviation_delta,
        ))
    for name in ("curtiss.228", "curtiss.229", "curtiss.506"):
        cases.append((
            "events/zzzzirmr_sports_curtiss_events.txt",
            "events/sports/curtiss_events.txt", name, aviation_delta,
        ))

    def trade_delta(items: list[str], number: int) -> list[str]:
        if number == 6:
            items = rewrite(
                items, "building_automotive_industry",
                "building_war_machine_industry", 2,
            )
            items = rewrite(
                items, "has_active_production_method = pm_tank_production", "", 2,
            )
            return rewrite(
                items, '"gfx/event_pictures/unspecific_devastation.bk2"',
                '"unspecific_devastation"', 1,
            )
        return rewrite(
            items, "has_active_production_method = pm_aeroplane_production",
            "is_building_type = building_aircraft_industry", 2,
        )

    for number in (6, 7):
        cases.append((
            "events/zzir_MFE_trade_good_events.txt",
            "events/MFE/MFE_trade_good_events.txt", f"MFE_trade_good_events.{number}",
            lambda items, n=number: trade_delta(items, n),
        ))
    loaders = set()
    for patch_file, upstream_file, name, transform in cases:
        patch, upstream = MOD / patch_file, args.mr / upstream_file
        key = name if patch_file.startswith("events/") else "REPLACE:" + name
        compare = compare_company if name.startswith("curtiss_company_") else equal

        def compare_case() -> None:
            compare(source(patch, key), transform(source(upstream, name)))

        check(f"{patch_file} / {name}", compare_case)
        loaders.add((patch, upstream))
    trade_path = MOD / "events/zzir_MFE_trade_good_events.txt"
    check(
        "events/zzir_MFE_trade_good_events.txt / MFE_trade_good_events.6 "
        "net_fixed_income > 2000",
        lambda: contains(
            source(trade_path, "MFE_trade_good_events.6"), "net_fixed_income > 2000",
        ),
    )
    loaders.add((
        MOD / "common/company_types/zzzzirmr_vanilla_company_types.txt",
        args.ir / "common/company_types/zir_companies.txt",
    ))
    for patch, upstream in sorted(loaders):
        check(
            f"{patch.relative_to(MOD)} / loader filename and definition rules",
            lambda p=patch, u=upstream: check_loader(p, u),
        )
    for language in LANGUAGES:
        check(
            f"localization/{language}/zzirmr_{language}.yml",
            lambda lang=language: check_locale(lang, args.mr),
        )
    # Also catch the obsolete key if a later change adds another locale file.
    for path in sorted((MOD / "localization").rglob("*.yml")):
        check(
            f"{path.relative_to(MOD)} / obsolete tooltip absence",
            lambda p=path: equal(
                [OBSOLETE_TT]
                if OBSOLETE_TT in p.read_text(encoding="utf-8-sig") else [],
                [],
            ),
        )
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"{len(failures)} failed; {passed} passed", file=sys.stderr)
        return 1
    print(
        f"PASS: {passed} offline compatibility checks "
        "(source comparisons, not in-game validation)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
