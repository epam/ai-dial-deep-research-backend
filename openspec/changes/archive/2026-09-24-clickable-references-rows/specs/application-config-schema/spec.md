## MODIFIED Requirements

### Requirement: The citation pill's title budget is per channel

`ApplicationProperties` SHALL expose a nullable integer field, `max_pill_title_chars`, saying how
much of a citation's **leading part** the citation pill shows, the ellipsis counted within it.

**The field SHALL default to null**, so a channel that names nothing gets every pill whole. A
shortened title leaves the reader guessing which publication the pill names, and a client with room
for the whole title gains nothing from the cut. A channel whose client has no such room sets a
number. The field SHALL have a floor below which a shortened label conveys nothing, and the floor
applies to the number a channel sets.

The budget governs the leading part of every inline pill label, whatever kind of source it names: a
cited document's publication title, and a cited dataset's name — or its URN, where no name resolved.
It does **not** govern the whole label of an inline pill. It also governs the label of a References
row's pill, which is a leading part with no trailing part. The field keeps the name
`max_pill_title_chars` although it covers more than a title, because renaming a channel property
breaks every configuration that sets it, and the cost of the slightly narrow name is smaller than
the cost of that break.

It is a **channel** setting rather than a server one: what fits on a pill depends on the client the
channel's readers use, not on which server the source came from. **report-citations** owns what the
app does with it — the popup card keeps the whole leading part whatever this says, and each kind of
inline citation's fixed trailing part, a document's cited page or a dataset's `dataset`, is appended
after the shortening so it is never lost to a long leading part.

**Null SHALL mean no shortening**, showing every title whole. That is the default and the supported
way to switch shortening off, and there SHALL be no separate flag for it.

#### Scenario: A channel narrows the pill label

- **WHEN** a channel sets `max_pill_title_chars` to a number and a report cites a document whose
  title is longer than that
- **THEN** the pill's label SHALL be shortened to that budget, and the citation card's SHALL still
  carry the whole title

#### Scenario: The budget applies to a dataset's name and to its URN

- **WHEN** a channel sets `max_pill_title_chars` and a report cites a dataset whose name is longer
  than that, and another whose name did not resolve and whose URN is longer than that
- **THEN** both pills SHALL carry their leading part shortened to that budget with `dataset` appended
  after the shortening, and both cards SHALL carry their leading part whole

#### Scenario: The budget applies to a References row's pill

- **WHEN** a channel sets `max_pill_title_chars` and a References row whose source can be opened
  carries a name longer than that
- **THEN** the row's pill SHALL carry the name shortened to that budget, and the row's citation card
  SHALL carry it whole

#### Scenario: A channel naming nothing gets whole pills

- **WHEN** `ApplicationProperties.model_validate` receives properties with no `max_pill_title_chars`
- **THEN** validation SHALL succeed, the field SHALL be null, and every pill SHALL carry its leading
  part whole

#### Scenario: A channel switches shortening off explicitly

- **WHEN** a channel sets `max_pill_title_chars` to null
- **THEN** validation SHALL succeed, and every pill SHALL carry its leading part whole, a dataset's
  name or URN as well as a document's title

#### Scenario: A budget too small to be useful is rejected

- **WHEN** a channel sets `max_pill_title_chars` to a number below the floor
- **THEN** validation SHALL raise a pydantic `ValidationError`
