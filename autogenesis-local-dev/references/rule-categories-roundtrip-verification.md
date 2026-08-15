# Rule Categories Roundtrip Verification (2026-05-29)

**Conclusion: Rule categories survive pack/unpack roundtrip correctly. The spinners display loaded values on dialog open.**

---

## Data Class Chain

```
MapData.writingAgentConfig: WritingAgentConfig  (MapPack.kt:82)
  └── ruleCategories: List<RuleCategory>        (WritingAgentConfig:49)
        └── RuleCategory(name, chancePercent, rules)  (RuleCategory:41-45)

InjectableRule(id, description, weight, category)  (InjectableRule:33-38)
```

All are `@Serializable`. The chain is complete end-to-end.

---

## Save Path

```
WritingSettingsDialog.buildConfigFromUI()  (WSD.kt:801)
  → categoryRulesValues[index] provides rules list
  → categorySpinnerValues[index] provides chancePercent
  → rebuiltCategories = RuleCategory(name, chancePercent, rules)
  → WritingAgentConfig(ruleCategories = rebuiltCategories, ...)
  → canvas.getMapData() → MapData(writingAgentConfig = canvas.writingAgentConfig)  (MapCanvas.kt:575)
  → MapPackManager.pack(imageName, imageBytes, mapData) → ZIP(map.json + image)
```

`MapCanvas.saveMapData()` passes the full `writingAgentConfig` at line 575 — rules list IS included.

---

## Load Path

```
MapPackManager.unpack(packBytes) → UnpackedMapPack(imageName, imageBytes, mapData)
  → canvas.loadFromPack(unpacked) → writingAgentConfig = unpacked.mapData.writingAgentConfig  (MapCanvas.kt:358)
  → TopBar opens WritingSettingsDialog(initialConfig = canvas.writingAgentConfig)
```

---

## Spinner Pre-population (Dialog Open)

```
init{} block (WSD.kt:101-132):
  categoryRulesValues.clear()
  categoryRulesValues.addAll(config.ruleCategories)         (115-116) — rules preserved
  categorySpinnerValues.clear()
  config.ruleCategories.forEachIndexed { index, category ->
      categorySpinnerValues[index] = category.chancePercent  (121-122)
  }

WritingSettingsCategorySection.renderInto() (WritingSettingsSection.kt:82):
  val renderedValue = categorySpinnerValues[index] ?: category.chancePercent
  spinner.value = renderedValue.toString()
  → categorySpinnerValues WAS pre-populated → spinner shows loaded value ✓
```

---

## Build Verification

```bash
./gradlew :sharedModel:jvmTest --tests "structs.MapPackManagerWritingSettingsTest" --rerun-tasks
# 6 tests, all PASS:
#   story weights survive pack unpack roundtrip ✓
#   rule categories with custom chancePercent survive pack unpack roundtrip ✓
#   all writing settings survive full pack unpack roundtrip ✓
#   default story weights serialize with encodeDefaults=true ✓
#   authorEnabled false survives pack unpack roundtrip ✓
```

Key assertions from `MapPackManagerWritingSettingsTest.kt`:
- `assertEquals(55, unpacked.mapData.writingAgentConfig.ruleCategories[0].chancePercent)` ✓
- `assertEquals("rule1", unpacked.mapData.writingAgentConfig.ruleCategories[0].rules[0].id)` ✓ — rules list preserved
- `assertEquals("Diplomacy", unpacked.mapData.writingAgentConfig.ruleCategories[0].name)` ✓

---

## Default Rule Categories

`getDefaultRuleCategories()` (WSD.kt:655-693):
| Name | chancePercent | Rules |
|------|--------------|-------|
| absurdity | 10 | 2 |
| time_reality | 8 | 1 |
| horror | 7 | 1 |
| geopolitics | 10 | 1 |
| general | 5 | 1 |

These are the defaults used only when a pack has no `ruleCategories` (empty list). When a pack has categories, those are used instead.

---

## Key Files

| File | Role |
|------|------|
| `sharedModel/src/commonMain/kotlin/structs/MapPack.kt` | `RuleCategory`, `WritingAgentConfig`, `MapData` data classes |
| `sharedModel/src/jsMain/kotlin/structs/MapPackManager.kt` | JSZip pack/unpack (browser) |
| `sharedModel/src/jvmMain/kotlin/structs/MapPackManager.kt` | ZipOutputStream/ZipInputStream (JVM) |
| `mapEditor/src/jsMain/kotlin/ui/WritingSettingsDialog.kt` | Dialog with `init{}` pre-population + `buildConfigFromUI()` |
| `mapEditor/src/jsMain/kotlin/ui/WritingSettingsSection.kt` | `WritingSettingsCategorySection.renderInto()` — raw DOM spinner |
| `sharedModel/src/jvmTest/kotlin/structs/MapPackManagerWritingSettingsTest.kt` | 6 integration tests |