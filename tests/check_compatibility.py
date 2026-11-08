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
URANIUM_GROUP = "irmr_pmg_uranium_glass"
IR_SYNTHETICS = ("building_synthetic_rubber_plant", "building_synthetic_fuel_plant")
MR_SYNTHETICS = (
    "building_mendelejew_hydrogenation_plants",
    "building_mendelejew_synthetic_rubber_factory",
)
INDUSTRY_LAWS = ("law_industry_banned", "law_extraction_economy")
INDUSTRY_TRIGGERS = (
    "has_heavy_industry_building", "is_heavy_industry_building",
    "is_production_building",
)
INDUSTRY_RESTRICTION = """
    owner = { NOT = { OR = {
        has_law_or_variant = law_type:law_industry_banned
        has_law_or_variant = law_type:law_extraction_economy
    } } }
"""
CODLING_PREDICATE = """
    OR = {
        is_building_type = building_wheat_farm
        is_building_type = building_maize_farm
        is_building_type = building_rye_farm
    }
    OR = {
        has_active_production_method = pm_apple_orchards
        has_active_production_method = pm_citrus_orchards
    }
"""
POTATO_BONUS = """
    if = {
        limit = { any_scope_state = { any_scope_building = {
            is_building_type = building_rye_farm
            has_active_production_method = pm_potatoes
        } } }
        multiply = 10
    }
"""


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


def check_loader(patch: Path, upstream: Path, *, first_event: bool = False) -> None:
    """Check additive filenames/load order and the two distinct override syntaxes."""
    if patch.name == upstream.name:
        raise AssertionError("full-file shadows are forbidden")
    ordered = patch.name < upstream.name if first_event else patch.name > upstream.name
    if patch.suffix != ".txt" or not ordered:
        order = "before" if first_event else "after"
        raise AssertionError(f"filename must load {order} {upstream.name}")
    definitions = blocks(tokens(patch.read_text(encoding="utf-8-sig")))
    if patch.parent == MOD / "events":
        if any(":" in name for name, _ in definitions):
            raise AssertionError("root events require bare IDs, not REPLACE:")
    elif patch.is_relative_to(MOD / "common"):
        new_ids = (
            {URANIUM_GROUP}
            if patch.parent == MOD / "common/production_method_groups" else set()
        )
        if any(
            not name.startswith("REPLACE:") and name not in new_ids
            for name, _ in definitions
        ):
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


def check_pottery_group(ir: Path) -> None:
    """Keep IR's ceramics-only group on pottery, clearing MR's glass injection."""
    name = "REPLACE:pmg_luxury_building_glassworks"
    expected = source(ir / "common/production_method_groups/zir_industry.txt", name)
    equal(one_block(expected, "production_methods"), ["pm_ceramics", "pm_bone_china"])
    equal(
        source(MOD / "common/production_method_groups/zzzzirmr_industry.txt", name),
        expected,
    )
    pottery = source(
        ir / "common/buildings/zir_industry.txt",
        "REPLACE_OR_CREATE:building_pottery_mill",
    )
    equal(
        one_block(pottery, "production_method_groups"),
        ["pmg_luxury_building_glassworks"],
    )


def check_uranium_group(ir: Path) -> None:
    """Reuse IR's refining texture with an off-first optional conversion list."""
    expected = source(
        ir / "common/production_method_groups/zir_industry.txt",
        "REPLACE:pmg_luxury_building_glassworks",
    )
    expected = rewrite(
        expected, "production_methods = { pm_ceramics pm_bone_china }",
        "production_methods = { pm_disabled_ceramics pm_curie_uranium_glass }", 1,
    )
    equal(
        source(
            MOD / "common/production_method_groups/zzzzirmr_industry.txt",
            URANIUM_GROUP,
        ),
        expected,
    )


def check_glassworks(ir: Path) -> None:
    """Append one group without changing any other current IR Glassworks field."""
    name = "REPLACE:building_glassworks"
    expected = source(ir / "common/buildings/zir_industry.txt", name)
    groups = "pmg_base_building_glassworks pmg_glassblowing"
    equal(one_block(expected, "production_method_groups"), tokens(groups))
    expected = rewrite(
        expected, f"production_method_groups = {{ {groups} }}",
        f"production_method_groups = {{ {groups} {URANIUM_GROUP} }}", 1,
    )
    equal(source(MOD / "common/buildings/zzzzzirmr_industry.txt", name), expected)


def check_uranium_recipe(game: Path, mr: Path) -> None:
    """Check MR's unchanged prerequisites/recipe against real base glass output."""
    uranium = source(
        mr / "common/production_methods/mr_science_curie_production_methods.txt",
        "pm_curie_uranium_glass",
    )
    equal(one_block(uranium, "unlocking_technologies"), ["verrier_radioactivity_tech"])
    equal(
        one_block(uranium, "unlocking_production_methods"),
        ["pm_crystal_glass", "pm_houseware_plastics"],
    )
    modifiers = one_block(uranium, "building_modifiers")
    equal(
        one_block(modifiers, "workforce_scaled"),
        tokens(
            "goods_input_good_uranium_add = 10 "
            "goods_output_glass_add = -55 goods_output_porcelain_add = 65",
        ),
    )
    equal(
        one_block(modifiers, "level_scaled"),
        tokens("building_employment_shopkeepers_add = 1000"),
    )
    base_methods = one_block(
        source(
            game / "common/production_method_groups/01_industry.txt",
            "pmg_base_building_glassworks",
        ),
        "production_methods",
    )
    industry = game / "common/production_methods/01_industry.txt"
    for name, net in (("pm_crystal_glass", 5), ("pm_houseware_plastics", 45)):
        if name not in base_methods:
            raise AssertionError(f"{name}: missing from base Glassworks group")
        workforce = one_block(
            one_block(source(industry, name), "building_modifiers"),
            "workforce_scaled",
        )
        output = int(workforce[workforce.index("goods_output_glass_add") + 2])
        equal([str(output - 55)], [str(net)])
    equal(
        source(industry, "pm_disabled_ceramics"),
        tokens(
            'texture = "gfx/interface/icons/production_method_icons/no_ceramics.dds"',
        ),
    )


def check_uranium_override_absence() -> None:
    """Leave pottery's building and all conversion/base recipes upstream-owned."""
    for folder, names in (
        ("buildings", {"building_pottery_mill"}),
        (
            "production_methods",
            {
                "pm_curie_uranium_glass", "pm_crystal_glass",
                "pm_houseware_plastics", "pm_disabled_ceramics",
            },
        ),
    ):
        for path in sorted((MOD / "common" / folder).rglob("*.txt")):
            for name, _ in blocks(tokens(path.read_text(encoding="utf-8-sig"))):
                if name.rsplit(":", 1)[-1] in names:
                    raise AssertionError(f"{path}: unexpected override {name}")


def check_synthetic_building(name: str, ir: Path, mr: Path) -> None:
    """Keep saved-building metadata and unlocks; change only construction access."""
    actual = source(
        MOD / "common/buildings/zzzzzirmr_heavy_industry.txt", "REPLACE:" + name,
    )
    if name in IR_SYNTHETICS:
        expected = source(
            ir / "common/buildings/zir_heavy_industry.txt", "REPLACE_OR_CREATE:" + name,
        )
        equal(one_block(expected, "possible"), tokens(INDUSTRY_RESTRICTION))
        expected = rewrite(
            expected, f"possible = {{ {INDUSTRY_RESTRICTION} }}",
            "possible = { always = no }", 1,
        )
        equal(one_block(actual, "possible"), tokens("always = no"))
    else:
        expected = source(
            mr / "common/buildings/mr_science_mendelejew_buildings.txt", name,
        )
        expected = rewrite(
            expected, "ownership_type = self",
            f"possible = {{ {INDUSTRY_RESTRICTION} }} ownership_type = self", 1,
        )
        equal(one_block(actual, "possible"), tokens(INDUSTRY_RESTRICTION))
    equal(actual, expected)


def check_industry_trigger(name: str, ir: Path) -> None:
    """Include both MR survivors without repairing unrelated upstream omissions."""
    predicate = "has_building" if name.startswith("has_") else "is_building_type"
    expected = source(
        ir / "common/scripted_triggers/zir_scripted_triggers.txt", "REPLACE:" + name,
    )
    anchor = f"{predicate} = building_synthetic_fuel_plant"
    additions = " ".join(f"{predicate} = {target}" for target in MR_SYNTHETICS)
    expected = rewrite(expected, anchor, f"{anchor} {additions}", 1)
    actual = source(
        MOD / "common/scripted_triggers/zzzzirmr_industry_triggers.txt",
        "REPLACE:" + name,
    )
    for target in MR_SYNTHETICS:
        contains(one_block(actual, "OR"), f"{predicate} = {target}")
    equal(actual, expected)


def check_industry_law(name: str, game: Path, ir: Path) -> None:
    """Preserve full IR/game law fields; remove MR plants only upon activation."""
    expected = source(ir / "common/laws/zir_economic_system.txt", name)
    vanilla = source(game / "common/laws/01_economic_system.txt", name)
    ir_activation = " ".join(one_block(expected, "on_activate"))
    game_activation = " ".join(one_block(vanilla, "on_activate"))
    equal(
        rewrite(expected, f"on_activate = {{ {ir_activation} }}", "", 1),
        rewrite(vanilla, f"on_activate = {{ {game_activation} }}", "", 1),
    )
    additions = " ".join(
        f"if = {{ limit = {{ has_building = {target} }} remove_building = {target} }}"
        for target in MR_SYNTHETICS
    )
    anchor = (
        "if = { limit = { has_building = building_synthetic_fuel_plant } "
        "remove_building = building_synthetic_fuel_plant }"
    )
    expected = rewrite(expected, anchor, f"{anchor} {additions}", 1)
    actual = source(
        MOD / "common/laws/zzzzirmr_economic_system.txt", "REPLACE:" + name,
    )
    states = one_block(
        one_block(one_block(actual, "on_activate"), "custom_tooltip"),
        "every_scope_state",
    )
    for target in MR_SYNTHETICS:
        contains(
            states,
            f"if = {{ limit = {{ has_building = {target} }} "
            f"remove_building = {target} }}",
        )
    equal(actual, expected)


def check_decree_event(name: str, ir: Path) -> None:
    """Extend eligibility and selection, preserving every other IR event token."""
    expected = source(ir / "events/_ir_decree_events.txt", name)
    anchor = "is_building_type = building_synthetic_fuel_plant"
    additions = " ".join(f"is_building_type = {target}" for target in MR_SYNTHETICS)
    expected = rewrite(expected, anchor, f"{anchor} {additions}", 2)
    actual = source(MOD / "events/__irmr_decree_events.txt", name)
    eligible = one_block(
        one_block(
            one_block(one_block(actual, "trigger"), "any_scope_state"),
            "any_scope_building",
        ),
        "OR",
    )
    selection = one_block(
        one_block(
            one_block(one_block(actual, "immediate"), "random_scope_state"),
            "random_scope_building",
        ),
        "limit",
    )
    for target in MR_SYNTHETICS:
        for factory_list in (eligible, one_block(selection, "OR")):
            contains(factory_list, f"is_building_type = {target}")
    equal(actual, expected)


def check_definition_scope(path: Path, names: tuple[str, ...]) -> None:
    """Reject accidental full-file copies or extra database overrides."""
    equal(
        [name for name, _ in blocks(tokens(path.read_text(encoding="utf-8-sig")))],
        ["REPLACE:" + name for name in names],
    )


def check_decree_scope(ir: Path) -> None:
    """Own only two bare IDs and one namespace; leave other IR events upstream."""
    patch = MOD / "events/__irmr_decree_events.txt"
    upstream = ir / "events/_ir_decree_events.txt"
    items = tokens(patch.read_text(encoding="utf-8-sig"))
    definitions = blocks(items)
    names = ("decree_events.100", "decree_events.101")
    equal([name for name, _ in definitions], list(names))
    for name, body in definitions:
        items = rewrite(items, f"{name} = {{ {' '.join(body)} }}", "", 1)
    equal(items, tokens("namespace = decree_events"))
    if (MOD / "events" / upstream.name).exists():
        raise AssertionError("IR decree file must not be shadowed")
    ir_names = {
        name for name, _ in blocks(tokens(upstream.read_text(encoding="utf-8-sig")))
    }
    for path in sorted((MOD / "events").rglob("*.txt")):
        for name, _ in blocks(tokens(path.read_text(encoding="utf-8-sig"))):
            if name.rsplit(":", 1)[-1] in ir_names:
                if path != patch or name not in names:
                    raise AssertionError(f"{path}: unexpected IR decree override {name}")


def check_silk_suppression_absence() -> None:
    """Do not restore the removed synthetic-silk/synthetics building tombstone."""
    for path in sorted((MOD / "common/buildings").rglob("*.txt")):
        for name, _ in blocks(tokens(path.read_text(encoding="utf-8-sig"))):
            if name.rsplit(":", 1)[-1] == "building_synthetics_plant":
                raise AssertionError(f"{path}: removed synthetics suppression returned")


def industry_delta(items: list[str], name: str) -> list[str]:
    """Allow only counted industry corrections and three current video aliases."""
    if name == "MFE_workplace_events.17":
        items = rewrite(
            items,
            '"is_building_type = building_furniture_manufactory NOT = { '
            'has_active_production_method = pm_no_luxuries } level >= 5"',
            '"is_building_type = building_luxury_furniture_manufactory level >= 5"',
            2,
        )
    elif name == "MFE_trade_good_events.14":
        items = rewrite(
            items, "has_active_production_method = pm_hardwood",
            "is_building_type = building_logging_camp "
            "modifier:goods_output_hardwood_add > 0", 3,
        )
    elif name in ("radio_component_shortage_mod", "gaudi_radio_mania_modifier"):
        return rewrite(
            items, "building_electrics_industry_throughput_add",
            "building_radio_industry_throughput_add", 1,
        )
    else:
        items = rewrite(
            items, "building_electrics_industry", "building_radio_industry", 2,
        )
    aliases = {
        "MFE_workplace_events.17": "southamerica_aristocrats",
        "MFE_workplace_events.20": "unspecific_world_fair",
        "MFE_trade_good_events.14": "europenorthamerica_gold_prospectors",
    }
    if name in aliases:
        alias = aliases[name]
        items = rewrite(
            items, f'"gfx/event_pictures/{alias}.bk2"', f'"{alias}"', 1,
        )
    return items


def check_industry_predicates(path: Path, name: str) -> None:
    """Pin each eligibility/selection/option gate without simulating game scopes."""
    actual = source(path, name)
    trigger = one_block(actual, "trigger")
    immediate = one_block(actual, "immediate")
    if name == "MFE_workplace_events.17":
        predicate = tokens(
            'T = "is_building_type = building_luxury_furniture_manufactory '
            'level >= 5" K = "2"',
        )
        equal(one_block(trigger, "MFE_country_has_building_trigger"), predicate)
        selection = one_block(one_block(immediate, "random_scope_state"), "limit")
        equal(one_block(selection, "MFE_state_has_building_trigger"), predicate)
    elif name in ("vikelas.312", "gaudi.1424"):
        eligible = one_block(trigger, "any_scope_state")
        selection = one_block(one_block(immediate, "random_scope_state"), "limit")
        for state in (eligible, selection):
            if name == "vikelas.312":
                contains(
                    state, "any_scope_building = { "
                    "is_building_type = building_radio_industry "
                    "is_under_construction = no "
                    "has_active_production_method = pm_radios }",
                )
            else:
                contains(
                    state, "any_scope_building = { "
                    "is_building_type = building_radio_industry }",
                )
                contains(
                    state, "any_scope_building = { "
                    "is_building_type = building_tesla_telegraph "
                    "has_active_production_method = pm_tesla_radio_station }",
                )
        if name == "gaudi.1424":
            contains(eligible, "percent >= 0.2")
    else:
        eligible = one_block(trigger, "any_scope_building")
        selection = one_block(one_block(immediate, "random_scope_building"), "limit")
        if name == "MFE_workplace_events.20":
            predicate = tokens(
                "is_building_type = building_radio_industry occupancy > 0.75 "
                "cash_reserves_ratio > 0.25 weekly_profit > 0 level >= 5 "
                "has_active_production_method = pm_radios",
            )
            contains(trigger, "has_technology_researched = radio")
            contains(trigger, "any_scope_war = { count > 0 }")
        else:
            predicate = tokens(
                "is_building_type = building_logging_camp "
                "modifier:goods_output_hardwood_add > 0 level >= 5",
            )
            options = [body for key, body in blocks(actual) if key == "option"]
            equal([str(len(options))], ["2"])
            state = one_block(options[0], "scope:hardwood_state")
            equal(
                one_block(one_block(state, "random_scope_building"), "limit"),
                predicate,
            )
            contains(
                one_block(options[1], "trigger"), "any_scope_building = { "
                "is_building_type = building_instrument_workshops }",
            )
            equal(
                one_block(one_block(options[1], "random_scope_building"), "limit"),
                tokens("is_building_type = building_instrument_workshops"),
            )
        equal(eligible, predicate)
        equal(selection, predicate)


def check_script_scope(
    path: Path, names: tuple[str, ...], namespace: str = "", *, bom: bool = True,
) -> None:
    """Own only the listed definitions/namespace and require BOM on new scripts."""
    data = path.read_bytes()
    if bom and not data.startswith(b"\xef\xbb\xbf"):
        raise AssertionError("new script must use UTF-8 BOM")
    items = tokens(data.decode("utf-8-sig"))
    definitions = blocks(items)
    equal([name for name, _ in definitions], list(names))
    for name, body in definitions:
        items = rewrite(items, f"{name} = {{ {' '.join(body)} }}", "", 1)
    equal(items, tokens(f"namespace = {namespace}" if namespace else ""))


def check_orchard_sources(ir: Path) -> None:
    """All four IR base methods produce fruit without the obsolete secondary PMG."""
    buildings = ir / "common/buildings/zir_agro.txt"
    orchard = source(buildings, "REPLACE_OR_CREATE:building_fruit_orchard")
    contains(
        orchard, "production_method_groups = { pmg_base_building_fruit_orchard "
        "pmg_harvesting_process_building_orchard }",
    )
    rye = source(buildings, "REPLACE:building_rye_farm")
    equal(
        one_block(rye, "production_method_groups"),
        tokens("pmg_base_building_rye_farm pmg_harvesting_process_building_rye_farm"),
    )
    methods = one_block(
        source(
            ir / "common/production_method_groups/zir_agro.txt",
            "REPLACE_OR_CREATE:pmg_base_building_fruit_orchard",
        ),
        "production_methods",
    )
    equal(methods, [
        "pm_simple_farming_orchard", "pm_soil_enriching_farming_orchard",
        "pm_fertilization_orchard", "pm_chemical_fertilizer_orchard",
    ])
    for method, output in zip(methods, (15, 25, 40, 60)):
        contains(
            one_block(one_block(source(
                ir / "common/production_methods/zir_agro.txt",
                "REPLACE_OR_CREATE:" + method,
            ), "building_modifiers"), "workforce_scaled"),
            f"goods_output_fruit_add = {output}",
        )


def check_codling_event(number: int) -> None:
    """Pin introductions on both eligibility and selection, including MR's flags."""
    year, region, level = {
        65: (1870, "north_america", 5),
        66: (1880, "oceania", 3),
        67: (1890, "south_africa", 3),
        68: (1900, "south_america", 3),
    }[number]
    actual = source(
        MOD / "events/zzzzirmr_science_theiler_events.txt", f"theiler.{number}",
    )
    trigger = one_block(actual, "trigger")
    contains(trigger, f"game_date >= {year}.1.1")
    flags = f"has_global_variable = theiler_codling_mouth_{region}_global_var "
    if number != 65:
        flags += (
            "has_global_variable = "
            f"theiler_stopped_codling_mouth_{region}_global_var "
        )
    equal(
        one_block(trigger, "NOR"),
        tokens(flags + "has_variable = theiler_codling_moth_prevention_var"),
    )
    state = f"is_in_geographic_region = geographic_region_{region} "
    if number != 65:
        state += "any_scope_building = { is_building_type = building_port } "
    state += (
        "any_scope_building = { is_building_type = building_fruit_orchard "
        f"level >= {level} }}"
    )
    equal(one_block(trigger, "any_scope_state"), tokens(state))
    equal(
        one_block(one_block(one_block(actual, "immediate"), "random_scope_state"),
                  "limit"),
        tokens(state),
    )


def check_codling_trigger() -> None:
    """Retain Australia's distinct region and the original prevention gate."""
    actual = source(
        MOD / "common/scripted_triggers/"
        "zzzzirmr_science_theiler_scripted_triggers.txt",
        "REPLACE:theiler_state_can_have_codling_moth_trigger",
    )
    regions = "is_in_geographic_region = theiler_geographic_region_codling_moth "
    for flag, region in (
        ("north_america", "north_america"), ("oceania", "australia"),
        ("south_america", "south_america"), ("south_africa", "south_africa"),
    ):
        regions += (
            f"AND = {{ has_global_variable = theiler_codling_mouth_{flag}_global_var "
            f"is_in_geographic_region = geographic_region_{region} }} "
        )
    equal(actual, tokens(
        f"any_scope_state = {{ OR = {{ {regions} }} "
        "any_scope_building = { is_building_type = building_fruit_orchard } "
        "owner = { theiler_has_codling_moth_prevention_trigger = no } }",
    ))


def check_pest_condition(name: str) -> None:
    """Keep four chance branches only; never move potato's dead 10x risk to a crop."""
    actual = source(
        MOD / "common/harvest_condition_types/zzzzirmr_theiler_harvest_condition_types.txt",
        "REPLACE:" + name,
    )
    codling = name == "theiler_codling_moth_condition"
    building = "is_building_type = building_fruit_orchard" if codling else """
        OR = { is_building_type = building_wheat_farm
               is_building_type = building_maize_farm
               is_building_type = building_rye_farm }
    """
    chance = "value = 0.0025 "
    for level, multiplier in ((5, 2), (10, 2), (15, 2), (20, 5)):
        chance += (
            "if = { limit = { any_scope_state = { any_scope_building = { "
            f"{building} level >= {level} }} }} }} multiply = {multiplier} }} "
        )
    equal(one_block(actual, "chance"), tokens(chance))
    contains(
        actual, "trigger = { theiler_state_can_have_"
        + ("codling_moth" if codling else "potato_beetle") + "_trigger = yes }",
    )
    equal(
        one_block(actual, "modifier"),
        tokens(f"goods_output_{'fruit' if codling else 'grain'}_mult = -0.25"),
    )
    equal(
        one_block(actual, "range"),
        tokens("integer_range = { min = 3 max = 3 }" if codling else
               "integer_range = { min = 4 max = 6 }"),
    )
    equal(one_block(actual, "duration"), tokens("fixed_range = { min = 250 max = 500 }"))
    equal(one_block(actual, "intensity"), tokens("fixed_range = { min = 1 max = 1 }"))


def check_locale(language: str, mr: Path) -> None:
    """Preserve translations, single-building scope and MR's uranium PM name."""
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
    if locale_value(text, URANIUM_GROUP) != '"$pm_curie_uranium_glass$"':
        raise AssertionError(f"{URANIUM_GROUP}: must reference MR's existing PM name")


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
    check(
        "pottery / ceramics and bone china only",
        lambda: check_pottery_group(args.ir),
    )
    check("uranium PMG / disabled first", lambda: check_uranium_group(args.ir))
    check(
        "Glassworks / preserve IR fields and append uranium group",
        lambda: check_glassworks(args.ir),
    )
    check(
        "uranium recipe / prerequisites, net glass 5/45 and disabled no conversion",
        lambda: check_uranium_recipe(args.game, args.mr),
    )
    check(
        "uranium / no pottery-building or recipe overrides",
        check_uranium_override_absence,
    )
    for name in IR_SYNTHETICS + MR_SYNTHETICS:
        check(
            f"{name} / preserved metadata and construction access",
            lambda n=name: check_synthetic_building(n, args.ir, args.mr),
        )
    for name in INDUSTRY_TRIGGERS:
        check(
            f"{name} / both MR factories and unchanged IR memberships",
            lambda n=name: check_industry_trigger(n, args.ir),
        )
    for name in INDUSTRY_LAWS:
        check(
            f"{name} / preserved fields and guarded MR removal on enactment",
            lambda n=name: check_industry_law(n, args.game, args.ir),
        )
    for name in ("decree_events.100", "decree_events.101"):
        check(
            f"{name} / both MR factories in eligibility and selection",
            lambda n=name: check_decree_event(n, args.ir),
        )
    for filename, names in (
        ("buildings/zzzzzirmr_heavy_industry.txt", IR_SYNTHETICS + MR_SYNTHETICS),
        ("scripted_triggers/zzzzirmr_industry_triggers.txt", INDUSTRY_TRIGGERS),
        ("laws/zzzzirmr_economic_system.txt", INDUSTRY_LAWS),
    ):
        check(
            f"common/{filename} / exact replacement scope",
            lambda f=filename, n=names: check_definition_scope(MOD / "common" / f, n),
        )
    check(
        "decrees / namespace, bare IDs and unshadowed IR events",
        lambda: check_decree_scope(args.ir),
    )
    check(
        "synthetics / removed silk suppression stays absent",
        check_silk_suppression_absence,
    )
    check(
        "decrees / first-definition filename order",
        lambda: check_loader(
            MOD / "events/__irmr_decree_events.txt",
            args.ir / "events/_ir_decree_events.txt", first_event=True,
        ),
    )
    check(
        "agriculture / all four IR orchard PMs produce fruit; rye has no secondary PMG",
        lambda: check_orchard_sources(args.ir),
    )
    for number in (65, 66, 67, 68):
        check(
            f"theiler.{number} / orchard introductions, dates, regions, flags and ports",
            lambda n=number: check_codling_event(n),
        )
    check(
        "codling trigger / orchard, original Australia region and prevention gate",
        check_codling_trigger,
    )
    for name in ("theiler_codling_moth_condition", "theiler_potato_beetle_condition"):
        check(
            f"{name} / exact chance scaling, penalties and duration; no dead 10x branch",
            lambda n=name: check_pest_condition(n),
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
    # Count the entire cereal+PM conjunction, not just its building-type OR list.
    for patch_file, upstream_file, names, count in (
        (
            "events/zzzzirmr_science_theiler_events.txt",
            "events/science/theiler_events.txt",
            tuple(f"theiler.{n}" for n in (65, 66, 67, 68)), 2,
        ),
        (
            "common/scripted_triggers/zzzzirmr_science_theiler_scripted_triggers.txt",
            "common/scripted_triggers/mr_science_theiler_scripted_triggers.txt",
            ("theiler_state_can_have_codling_moth_trigger",), 1,
        ),
        (
            "common/harvest_condition_types/zzzzirmr_theiler_harvest_condition_types.txt",
            "common/harvest_condition_types/theiler_harvest_condition_types.txt",
            ("theiler_codling_moth_condition",), 4,
        ),
    ):
        for name in names:
            cases.append((
                patch_file, upstream_file, name,
                lambda items, c=count: rewrite(
                    items, CODLING_PREDICATE,
                    "is_building_type = building_fruit_orchard", c,
                ),
            ))
    cases.append((
        "common/harvest_condition_types/zzzzirmr_theiler_harvest_condition_types.txt",
        "common/harvest_condition_types/theiler_harvest_condition_types.txt",
        "theiler_potato_beetle_condition",
        lambda items: rewrite(items, POTATO_BONUS, "", 1),
    ))
    for patch_file, upstream_file, name in (
        (
            "events/zzzzirmr_sports_vikelas_events.txt",
            "events/sports/vikelas_events.txt", "vikelas.312",
        ),
        (
            "events/zzzzirmr_arts_gaudi_events.txt",
            "events/arts/gaudi_events.txt", "gaudi.1424",
        ),
        *(
            (
                "events/zzzzirmr_MFE_workplace_events.txt",
                "events/MFE/MFE_workplace_events.txt", f"MFE_workplace_events.{n}",
            )
            for n in (17, 20)
        ),
        (
            "events/zzir_MFE_trade_good_events.txt",
            "events/MFE/MFE_trade_good_events.txt", "MFE_trade_good_events.14",
        ),
        (
            "common/static_modifiers/zzzzirmr_industry_modifiers.txt",
            "common/static_modifiers/MFE_mods.txt", "radio_component_shortage_mod",
        ),
        (
            "common/static_modifiers/zzzzirmr_industry_modifiers.txt",
            "common/static_modifiers/mr_science_tesla_modifiers.txt",
            "gaudi_radio_mania_modifier",
        ),
    ):
        cases.append((
            patch_file, upstream_file, name,
            lambda items, n=name: industry_delta(items, n),
        ))
        if patch_file.startswith("events/"):
            check(
                f"{name} / corrected industry eligibility, selection and options",
                lambda p=patch_file, n=name: check_industry_predicates(MOD / p, n),
            )
    for name, value in (
        ("radio_component_shortage_mod", "-0.1"),
        ("gaudi_radio_mania_modifier", "0.1"),
    ):
        check(
            f"{name} / exact radio throughput {value}",
            lambda n=name, v=value: contains(
                source(
                    MOD / "common/static_modifiers/zzzzirmr_industry_modifiers.txt",
                    "REPLACE:" + n,
                ),
                f"building_radio_industry_throughput_add = {v}",
            ),
        )
    for filename, names, namespace, bom in (
        (
            "events/zzzzirmr_science_theiler_events.txt",
            tuple(f"theiler.{n}" for n in (65, 66, 67, 68)), "theiler", True,
        ),
        (
            "common/scripted_triggers/zzzzirmr_science_theiler_scripted_triggers.txt",
            ("REPLACE:theiler_state_can_have_codling_moth_trigger",), "", True,
        ),
        (
            "common/harvest_condition_types/zzzzirmr_theiler_harvest_condition_types.txt",
            ("REPLACE:theiler_codling_moth_condition",
             "REPLACE:theiler_potato_beetle_condition"), "", True,
        ),
        (
            "events/zzzzirmr_sports_vikelas_events.txt", ("vikelas.312",),
            "vikelas", True,
        ),
        (
            "events/zzzzirmr_arts_gaudi_events.txt", ("gaudi.1424",), "gaudi", True,
        ),
        (
            "events/zzzzirmr_MFE_workplace_events.txt",
            ("MFE_workplace_events.17", "MFE_workplace_events.20"),
            "MFE_workplace_events", True,
        ),
        (
            "events/zzir_MFE_trade_good_events.txt",
            tuple(f"MFE_trade_good_events.{n}" for n in (6, 7, 14)),
            "MFE_trade_good_events", False,
        ),
        (
            "common/static_modifiers/zzzzirmr_industry_modifiers.txt",
            ("REPLACE:radio_component_shortage_mod", "REPLACE:gaudi_radio_mania_modifier"),
            "", True,
        ),
    ):
        check(
            f"{filename} / exact definition scope, namespace and encoding",
            lambda f=filename, n=names, ns=namespace, b=bom: check_script_scope(
                MOD / f, n, ns, bom=b,
            ),
        )
    for patch_name, name, game_file, game_name in (
        (
            "zzzzirmr_MFE_workplace_events.txt", "MFE_workplace_events.17",
            "treaty_of_london_events.txt", "treaty_of_london_events.1",
        ),
        (
            "zzzzirmr_MFE_workplace_events.txt", "MFE_workplace_events.20",
            "grand_exhibition_events.txt", "exhibition_events.1",
        ),
        (
            "zzir_MFE_trade_good_events.txt", "MFE_trade_good_events.14",
            "gold_rush.txt", "goldrush.1",
        ),
    ):
        check(
            f"{name} / video alias matches supplied 1.15 game",
            lambda p=patch_name, n=name, f=game_file, g=game_name: equal(
                one_block(source(MOD / "events" / p, n), "event_image"),
                one_block(source(args.game / "events" / f, g), "event_image"),
            ),
        )
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
    loaders.add((
        MOD / "common/buildings/zzzzzirmr_industry.txt",
        args.ir / "common/buildings/zir_industry.txt",
    ))
    loaders.update({
        (
            MOD / "common/buildings/zzzzzirmr_heavy_industry.txt",
            args.ir / "common/buildings/zir_heavy_industry.txt",
        ),
        (
            MOD / "common/buildings/zzzzzirmr_heavy_industry.txt",
            args.mr / "common/buildings/mr_science_mendelejew_buildings.txt",
        ),
        (
            MOD / "common/scripted_triggers/zzzzirmr_industry_triggers.txt",
            args.ir / "common/scripted_triggers/zir_scripted_triggers.txt",
        ),
        (
            MOD / "common/laws/zzzzirmr_economic_system.txt",
            args.ir / "common/laws/zir_economic_system.txt",
        ),
    })
    loaders.add((
        MOD / "common/production_method_groups/zzzzirmr_industry.txt",
        args.mr / "common/production_method_groups/"
        "mr_vanilla_production_method_groups_inject.txt",
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
