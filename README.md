# [1.15] Industry Realism + Morgenrote Compatch

Compatibility patch for Industry Realism (IR) and Morgenrote (MR).
**New campaign required. No migration or support for 1.13/1.14 saves.**
Back up personal saves and use only a disposable campaign for smoke testing.

**Law warning:** enacting **Industry Banned** or **Extraction Economy** removes
the surviving MR synthetic fuel and synthetic rubber factories. This is deliberate
law-enactment behavior, not a consequence of installing the patch. The patch does
not perform save-load cleanup or automatically migrate/delete saved buildings.

## Supported source snapshots

| Component | Source baseline |
| --- | --- |
| Victoria 3 | Supplied **1.15.0** scripts; launcher compatibility advertised as `1.15.*` |
| Industry Realism | Revision `79f8b8167144af34affb9b380d242084ef214d03` (`[1.15] Industry Realism`) |
| [Morgenrote](https://steamcommunity.com/sharedfiles/filedetails/?id=2889925770) | **2.9.0c Curie** |
| [Community Mod Framework (CMF)](https://steamcommunity.com/sharedfiles/filedetails/?id=3385002128) | **1.67.2** |

These are **static source-validation baselines, not an in-game test claim**.
The supplied game backup is not a runnable full installation. Runtime verification
below remains a release gate. Workshop updates, other 1.15 patches, and different
IR revisions need revalidation; arbitrary third-party mods are not covered.

## Installation and load order

1. Install the required CMF, MR, and IR versions above.
2. Use this repository's **`mod/` directory as the actual local mod root**, not the
   repository root. Register that directory with your local mod installation, or
   copy its contents into one local mod directory, including hidden `.metadata/`.
   The resulting root must contain `.metadata/metadata.json`, `common/`, `events/`,
   and `localization/` side by side; avoid an extra nested `mod/mod/` directory.
3. Arrange the playset in this order, with the patch last:
   **CMF → Morgenrote → Industry Realism → this patch**.
4. Start a **new campaign**, not an existing 1.13/1.14 campaign.

MR requires CMF. The patch's dependency metadata is intentionally not populated
with a guessed IR ID: the supplied IR metadata has an empty ID. Ensure all four
components are enabled yourself. Alternate orders are not supported. Launcher
order alone does not prove database merge behavior or event precedence.

## Integration decisions

- **Companies and aviation:** retain current company fields and copper extensions;
  use IR's dedicated aircraft factories for pilot schools, airlines, trophy
  scoring, aircraft bonuses, and aircraft-related event requirements.
- **Military academia:** both player UI and AI accept a level-5 **tank or aircraft**
  factory, not cars. Original arms, munitions, and artillery alternatives and other
  academic eligibility gates remain.
- **Uranium glass:** retain MR's optional conversion on **Glassworks**, off by
  default. It requires MR's radioactivity technology and a valid crystal-glass or
  houseware-plastics base method. Pottery retains standalone ceramics/bone china;
  base glass output is not replaced by a duplicate uranium recipe.
- **Synthetic industry:** only MR's fuel/rubber factories remain constructible,
  with their MR journal-technology unlocks. IR duplicates retain their metadata but
  are unavailable for new construction. Shared industrial triggers and decrees
  recognize MR factories. Both economic laws above block their construction and
  remove them **on enactment**; returning to a permissive law allows construction
  again. There is no installation-time deletion.
- **Radio, furniture, hardwood:** target IR radio and luxury-furniture factories;
  hardwood events recognize IR logging camps with positive hardwood output.
  Preserve original thresholds, rewards, penalties, and unrelated options.
- **Agricultural pests:** use IR fruit orchards for all 13 codling-moth predicates,
  retaining dates, regions, prevention, chance scaling, and fruit penalties.
  Remove potato beetle's dead 10× bonus without assigning that risk to another crop;
  retain its other chance logic and effects.

## Static validation

Run from the repository root with stdlib **Python 3.10+**. Supply source roots
containing `common/` and `events/`; no packages or test framework are needed.
For the supplied source locations, the exact command is:

```sh
python3 tests/check_compatibility.py \
  --game /home/soichiro/Documents/v3_backups/game_1_15_0 \
  --ir /home/soichiro/repos/vic3-modding/victoria3-mod-industry-realism/mod \
  --mr /steam/SteamLibrary/steamapps/workshop/content/529340/2889925770
git diff --check
```

Replace the three paths for another installation. Success prints
`PASS: ... offline compatibility checks (source comparisons, not in-game validation)`.
Failures identify the relevant file, symbol, or database; missing/unreadable
source files are errors, not skipped tests.

The checker covers all patch script structure, UTF-8 BOMs, unique IDs per database,
replacement target existence, the integration's changed building/production-method/
trait/modifier references, supported metadata, and matching localization keys,
headers, and BOMs in all 11 languages. Focused source-derived comparisons preserve
upstream fields except the approved deltas and check event eligibility as well as
selected scopes/options. This is not a Clausewitz interpreter: it cannot establish
dynamic scope correctness, natural event reachability, engine merge behavior,
rendering, or compatibility of every upstream combination.

## Manual runtime verification — pending

Use a dependency-complete **CMF → MR → IR → patch** playset and a disposable
**new 1836 campaign**. Record exact versions and playset order. First collect logs
from an equivalent no-patch baseline; distinguish pre-existing upstream errors
from new patch-attributable errors. Prepare positive/negative test states using
debug tools or a disposable later-game test save, never a personal campaign.
Check natural trigger eligibility separately: manually firing an event does not
prove that its normal trigger is reachable.

| Area | Positive check | Negative/regression check |
| --- | --- | --- |
| Startup and precedence | Main menu and fresh campaign load; 1.15 metadata accepted; intended patch definitions take effect, including decree events | No new missing-definition, invalid-scope, parse, or duplicate-definition errors attributable to patch |
| Companies | Intended IR/MR charters and copper additions visible; airline aircraft extension works | No charter targets a suppressed rubber factory; unrelated company fields retained |
| Uranium glass | Optional Glassworks conversion works after both technology and base-PM prerequisites; net base glass output remains nonnegative | Pottery keeps only ceramics/bone china; uranium absent without valid base; bonus/input not duplicated |
| Synthetic industry | Only MR fuel/rubber factories constructible after their MR journal technology; industrial triggers/decrees recognize them | IR duplicates unavailable; no installation-time deletion or lost building metadata |
| Economic laws | Both laws block MR factory construction; enacting either removes both MR factories | Other law fields/removal targets unchanged; permissive law permits construction again |
| Aviation | Pilot school, trophy scoring, airline factory creation, aircraft bonuses work | Car/tank-only industry cannot meet aircraft-specific requirements |
| Academia | Player UI and AI accept tanks or aircraft at level 5, plus original arms/munitions/artillery alternatives | Car-only and level-4 fail; university/army/government/confusion gates preserved |
| Radio | Sports radio, wartime shortage, first-program events find valid states; bonuses/penalties affect radio output | Telephone-only states cannot qualify |
| Furniture | Luxury factory qualifies and both event options work | Ordinary furniture alone cannot trigger the luxury event |
| Hardwood | Level-5 IR logging camp qualifies with normal base PM; both options work | Below-threshold and non-hardwood producers cannot qualify |
| Codling moth | Correct dated/regional introductions, natural chance at levels 5/10/15/20, fruit penalties, pesticide removal | Cereal-only states fail orchard checks; prevention blocks disease |
| Potato beetle | Normal eligibility/effects retained | No hidden 10× risk reassigned to rye or another crop |
| Localization and media | English plus one non-English UI render names/requirements; event media renders | No raw stale keys; all other locales retain matching complete keys |
| Stability | Advance multiple monthly ticks, save, reload the disposable 1.15 campaign | No patch-specific recurring log errors |

Do not mark the patch “tested in game” until this matrix is completed on a full
installation. Record outcomes and baseline differences rather than claiming the
entire upstream mod stack is error-free.

## Maintainer notes

- Keep overrides definition-scoped. Existing `common/` overrides use `REPLACE:`;
  the new `irmr_pmg_uranium_glass` group is additive. Do not shadow whole upstream
  files. Preserve IDs, source attribution, thresholds, and unrelated fields.
- Root `events/` files use bare IDs and namespaces. MR is the later-definition
  case used here; IR decree events use first-definition precedence, so
  `__irmr_decree_events.txt` must sort before `_ir_decree_events.txt`. The PMG patch
  must sort after both MR's injection file and IR's `zir_industry.txt`. Recheck
  actual engine behavior independently of launcher order.
- Save scripts and localization as UTF-8 with BOM. Keep localization headers,
  filename suffixes, and complete key sets aligned across all 11 languages.
- After upstream updates, re-read affected definitions and rerun source comparisons.
  Update the checker's scoped changed-reference list when adding integrations.
  It inventories declaration IDs only in relevant upstream databases, not all
  upstream gameplay. An upstream base Glassworks recipe override requires a new
  uranium-output review; do not silently retain the old net-output assertion.
- Keep framework internals, unrelated upstream gameplay/translation defects, and
  unrelated IR omissions out of this compatibility patch. Complete a fresh
  whole-change review and the runtime matrix before release.
