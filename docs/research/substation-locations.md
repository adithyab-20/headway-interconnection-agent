# Research: where substation locations come from

*Research note, October 2026 (ticket #37). Sentences marked **Inference** are my own reasoning.
Everything else is attributed to the linked source. "Measured here" figures come from a
throwaway script run against `data/publicqueuereport.xlsx`, the reviewed alias table
(`src/interconnection_agent/poi/aliases.csv`) and one bulk OpenStreetMap download made on
2026-10-05. They are not reproduced by tested code.*

## Summary

- **OpenStreetMap (OSM)** is the only source we found that is current, covers CAISO's area, and
  lets us show the coordinates on a public website. Its licence, the Open Database License
  (ODbL), asks for a visible credit on the map. Our name-to-coordinates table should be published
  under the same licence.
- **Measured here:** OSM has an exact-name match in the right place for 89 of the 166 station
  names (POIs, points of interconnection: where a project connects to the grid) on the active
  queue. Those cover **47,082 MW (61.7%)** of active net MW. Three more turn up
  under a variant spelling and four more only as a neighbouring power plant. With those, a
  reviewer can place **96 names, 51,701 MW (67.8%)**.
- Of the rest, **37 names (11,855 MW, 15.5%) are transmission lines**, not substations, so they
  have no single point. **31 names (12,416 MW, 16.3%)** are not in OSM by name, including new or
  planned substations. These fall back to their county.
- Matching by name alone is not safe. 11 names match two or more OSM substations in different
  places (for example "Midway" and "Red Bluff"), and two match the wrong one. A county check
  catches all of these.
- No alternative works for a public site. **EIA** has plant but not substation coordinates. The **California Energy
  Commission** layer now needs a login and mixes in commercial data. **Utility maps** show
  distribution substations under registration or company-property terms.

## 1. How many of our substations OpenStreetMap has

**What was measured.** The active sheet has 270 projects and 76,287 net MW. Their station names
fall into 166 distinct names after the alias table: 164 canonical names and 2 unmapped strings.
By MW, 79% of the active queue is in California, 10% in Nevada, 10% in Arizona and 2% in Mexico.
So the OSM query covered California, Nevada, Arizona and Baja California.

One bulk [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) query fetched every
OSM feature tagged `power=substation`, plus every named `power=plant`, in those four areas.
(Overpass is a public read-only search service over OSM data. A *tag* is OSM's key=value label
on a feature.) The mirror's data was dated 2026-07-15. It returned **5,998 substations, of which
only 1,828 (30%) have a name**, plus 1,581 named power plants.

Matching rule: lower-case both sides, then drop the voltage and words like "Substation",
"Switchyard", "Switching Station", "PP" and utility prefixes. A name counts as found only on
exact equality, the same rule the product will use at runtime. For each hit I compared the
voltage tag and looked up the hit's county from its coordinates with the
[Census Bureau geocoder](https://geocoding.geo.census.gov/geocoder/). Results by active net MW:

| Outcome | Names | Distinct substations | Net MW | Share |
|---|---|---|---|---|
| Exact name match to an OSM substation, right county | 89 | 66 | 47,082 | 61.7% |
| Found in OSM under a variant spelling (needs an alias) | 3 | 3 | 1,394 | 1.8% |
| Only a neighbouring OSM power plant matches (approximate point) | 4 | 4 | 3,225 | 4.2% |
| Same name, wrong place (false match) | 2 | 2 | 315 | 0.4% |
| Not in OSM by name | 31 | 28 | 12,416 | 16.3% |
| Transmission line, not a substation | 37 | 37 | 11,855 | 15.5% |
| **Total** | **166** | | **76,287** | **100%** |

The **voltage** check (220 and 230 kV treated as one level): 74 of the 89 exact matches
(43,040 MW) carry an OSM `voltage` tag that includes our voltage, 14 omit it and one has no tag.
**Inference:** the omissions are OSM listing only the main voltages (Los Banos: our 70 kV, OSM
500/230 kV), not wrong locations.

The **county** check: 87 of the 89 exact matches fall inside a county the queue lists for that
name. The other two are right anyway. Tesla 500 kV projects are in San Joaquin County, but the
substation is just over the line in Alameda. Innovation is listed as "CLARK/NYE". **Inference:**
the queue's County column is the project's site, not the substation's. So a county mismatch
should prompt a reviewer's look, not an automatic rejection.

**Representative hits:** Windhub, Whirlwind, Vincent and Lugo (SCE, tagged `500000;220000`).
Gates, Midway, Los Banos and Tesla (PG&E). Hoodoo Wash and Delaney (Arizona). Eldorado and
Mohave (Nevada).

**Same-name traps a county check resolves:** "Midway" (Kern vs. Imperial County), "Red Bluff"
(Riverside vs. Tehama), "Walnut" (Los Angeles vs. Stanislaus), "Mira Loma" (California vs.
Washoe County, Nevada).

**False matches:** "Ocotillo Switchyard 500 kV" (Imperial County) hits an APS power plant in
Maricopa County. "Valley Substation 138 kV" (Nye County, Nevada) hits SCE's Valley Substation in
Riverside County.

**Variant spellings a reviewer would add:** OSM has "Lighthipe Substation" (ours: "Litehipe"),
"Gamebird Switchard" (a typo in OSM) and "Hassayampa Switch Yard" (ours: "Hassayampa Common
Bus"). "Mustang Substation (75)" in OSM is a Cal Poly substation, not PG&E's Mustang, so it is a
trap too.

**Biggest misses:** Trout Canyon 230 kV (3,000 MW, Nevada). Tranquility 230 kV (1,575 MW; OSM
has only the nearby solar plants). East County 500/230 kV (1,273 MW). Arco 230/70 kV (975 MW).
The two Nevada names Lathrop Wells and Beatty. Two unmapped planned stations:
"Tehachapi Conceptual Substation #1" and "Proposed Lee Lake Substation". **Inference:** some
misses are probably in OSM without a name, since 70% of OSM substations here are unnamed. Planned
substations will never be in OSM until they are built.

**Transmission-line names** ("Manning-Midway 500 kV Line", "Delaney-Colorado River 500 kV
Line") name a tap on a line between two substations. **Inference:** a single dot would be
invented. Use the county, or later draw the line from OSM's `power=line` features.

## 2. What OSM's licence (ODbL) requires

OSM data is licensed under the Open Database License
([OSM copyright page](https://www.openstreetmap.org/copyright)). The ODbL distinguishes two
kinds of output ([ODbL 1.0, section 1](https://opendatacommons.org/licenses/odbl/1-0/)):

- A **Derivative Database** is a database "based upon the Database", including any adaptation
  of it or of a substantial part of its contents.
- A **Produced Work** is something made by using the data, "such as an image". A rendered map is
  the typical example.

**(a) Showing OSM-derived points on a public map.** The map picture is a Produced Work. Using one
publicly requires a notice telling users that the content came from OSM and is available under
the ODbL ([ODbL §4.3](https://opendatacommons.org/licenses/odbl/1-0/)). The OSM Foundation's
[Attribution Guidelines](https://osmfoundation.org/wiki/Licence/Attribution_Guidelines) (edited
10 September 2026) say what that looks like in practice:

- credit "OpenStreetMap" and say the data is under the ODbL;
- put it in a corner of the map, or next to it;
- link it to `openstreetmap.org/copyright`;
- show it without the user having to click. It may collapse after interaction or after five
  seconds, if it stays findable.

The [copyright page](https://www.openstreetmap.org/copyright) asks for credit to "OpenStreetMap
and its contributors".

A caveat on downloads. The OSMF
[Produced Work guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Produced_Work_-_Guideline)
says output "intended for the extraction of the original data" is a database, not a Produced
Work. **Inference:** if the site offers the substation points as a GeoJSON or CSV download or
API, that file is a database and the rules in (b) apply to it.

**(b) The name-to-coordinates table committed to a public repo.** There are two readings.

1. *It is a Derivative Database.* Then publishing it ("Publicly Convey") requires:
   - releasing it only under the ODbL or a compatible licence;
   - including the licence or its URL;
   - keeping OSM's notices intact ([§4.2, §4.4](https://opendatacommons.org/licenses/odbl/1-0/)).

   Anyone who receives it must also be offered the database itself, or a file of the changes
   ([§4.6](https://opendatacommons.org/licenses/odbl/1-0/)). The share-alike rule covers only
   that table. The OSMF
   [Collective Database guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Collective_Database_Guideline_Guideline)
   says linking OSM and non-OSM data by key or name does not by itself pull the non-OSM data
   under the ODbL. Our queue data and risk scores stay under their own terms.
2. *It is not "substantial", so the ODbL's database rules do not bite.* The
   [Substantial guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Substantial_-_Guideline)
   treats fewer than 100 features as insubstantial, but counts repeated small extractions as one.
   The [Geocoding guideline](https://osmfoundation.org/wiki/Licence/Community_Guidelines/Geocoding_-_Guideline)
   (endorsed 2017-08-24) says a collection of results is not a substantial extract when two
   things hold. First, it holds only names and latitude/longitude. Second, it is "not a
   systematic attempt" to gather all or nearly all features of one type across a city-sized or
   larger area. Even then, attribution under §4.3 is still required.

**Inference:** our table (70 to 100 substations picked because they are in the queue, out of
about 6,000 OSM substations here) plausibly fits reading 2. But it sits near the 100-feature line
and grows with each queue update. Releasing it under the ODbL costs almost nothing and removes
the question.

## 3. Alternatives and their access and licence limits

**EIA** (U.S. Energy Information Administration). Form EIA-860 publishes power plants with
"latitude, and longitude", but EIA does not publish substation locations
([EIA FAQ](https://www.eia.gov/tools/faqs/faq.php?id=567&t=3)). The 2025 final data came out
2026-09-10 ([EIA-860](https://www.eia.gov/electricity/data/eia860/)). EIA content is public
domain; EIA asks for a "Source: U.S. Energy Information Administration" credit with a date
([EIA reuse policy](https://www.eia.gov/about/copyrights_reuse.php)). **Verdict:** useful only
for the few POIs named after a plant (Moss Landing, Diablo Canyon, Contra Costa PP, Kern PP).
There, the plant's point is a fair stand-in for its switchyard. *Unconfirmed:* I did not match
EIA-860 against our names.

**California Energy Commission (CEC) "California Electric Substations".** A 2023 copy's metadata
([CDFW BIOS ds1199](https://filelib.wildlife.ca.gov/public/Metadata/CDFW_BIOS/ds1199_fgdc.xml))
describes 4,442 points. It has Name, Owner, Max_Voltage, County, Latitude and Longitude fields.
Its sources include commercial "GE and Platts" datasets. The use statement is only a disclaimer
and gives no licence. The CEC feature service those copies point to
(`services3.arcgis.com/bWPjFyq029ChCGur/.../Substation/FeatureServer/0`) answered "Token
Required" on 2026-10-05, and CEC's public ArcGIS organisation lists no substation item
(measured here). **Inference:** CEC has withdrawn the public layer, and with commercial Platts
inputs the right to republish its coordinates is unclear. **Verdict:** best coverage on paper,
but not usable publicly without CEC's explicit permission.

**Utility hosting-capacity maps.** These are integration-capacity-analysis (ICA) maps, which
show how much new generation each part of a utility's local grid can take.

- **PG&E** [GRIP](https://grip.pge.com/): its
  [user guide](https://www.pge.com/assets/pge/docs/about/doing-business-with-pge/pge-grip-user-guide.pdf)
  says it needs no login and has an open API. But its substation layer is "Substations,
  Distribution", and the portal's notice says the data are "PG&E's intellectual property". Users
  agree not to use it "beyond its intended use" (distribution planning).
- **SCE** [DRPEP](https://drpep.sce.com/drpep/?page=Page): shows substations and circuits.
  *Unconfirmed:* I could not read its terms of use (the page is a script-only app).
- **SDG&E**: you must
  [register with SDG&E](https://www.sdge.com/interconnection-information-and-map) to view the
  map. The map centres on distribution substations.

**Verdict:** these maps mostly cover distribution substations rather than the transmission
substations CAISO POIs name, and their terms do not allow republishing.

## Recommendation

1. **Use OpenStreetMap as the single location source.** The offline helper should:
   - suggest matches by exact normalized name;
   - show each candidate's OSM ID, operator, voltage tag and county;
   - flag any name with more than one candidate or a county mismatch.

   A person accepts each row into a checked-in table, recording the OSM element ID, latitude,
   longitude and the OSM data date. Runtime lookups stay exact-match.
2. **Expected coverage after review:** about **96 names and 51,700 MW (68%) of active net MW**
   get a real point, about 80% of the MW whose POI is a substation. The other 32% falls back to
   its county: line POIs (15.5%), names not in OSM (16.3%), and the two false matches.
   **Inference:** looking for unnamed OSM substations in the right county could recover part of
   the 16.3%.
3. **Licence obligations the product must meet:**
   - put a visible "© OpenStreetMap contributors, ODbL" credit, linked to
     `openstreetmap.org/copyright`, on the map (§4.3 and the OSMF Attribution Guidelines);
   - keep the coordinate table in its own file and mark it as derived from OSM under the ODbL,
     with the licence URL and OSM's notice (§4.2, §4.4);
   - apply the same terms to any download or API of the points.

   The rest of the repo's data stays under its current terms (Collective Database guideline).
   If EIA-860 is used for plant-named POIs, add EIA's dated source credit.
4. **Do not use** the CEC layer or utility maps as a data source for the public site.

**Open questions**

- Should the table be released under the ODbL from day one? That is the safe reading, and it is
  recommended here. The alternative is to rely on the Geocoding guideline's "insubstantial"
  reading.
- How should transmission-line POIs (15.5% of MW) be drawn? County only, or as OSM line
  segments?
- Should the site offer a downloadable point layer at all? If yes, it carries the ODbL.
- Would CEC grant explicit permission to republish its substation layer? It could fill the
  misses OSM has.
