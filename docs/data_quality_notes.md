# Data-quality notes: what went wrong and how it was fixed

| # | Problem found | Cause | Fix | Test |
|---|---|---|---|---|
| 1 | Phone shown as `8030000001.0`, leading zero lost | pandas guessed a float when a column had blanks; Excel stored the number without its zero | Read every cell as text; restore the leading zero, strip `.0` | `test_phone_keeps_leading_zero`, `test_legacy_default_dtype_bug_is_real` |
| 2 | Serial numbers shown as `3.0`; dates shown with `00:00:00` | Same type-guessing | Text reading, ISO dates | `test_dates_are_iso_...` |
| 3 | Header row not at the top | Title rows above the header, different in each file | Scan the first 50 rows; require 3+ header keywords so a title line isn't mistaken for the header | `test_header_found_below_title_rows`, `test_title_row_alone_is_not_a_header` |
| 4 | Same column spelled several ways | Free-typed headers ("ORIN ", "Orin", "Phone No") | Regex mapping to one canonical schema | end-to-end test |
| 5 | Source files deleted after conversion | Original script removed each Excel on success | Cleaning is non-destructive; originals are never touched | n/a |
| 6 | Name typed in different word order or case | Manual entry | Order-insensitive `name_key` | `test_name_key_ignores_order_case_and_spacing` |
| 7 | Handwritten date "14th feb 19th" silently parsed as 2019-02-14 | Two-digit year guessed by the date library | Require a four-digit year, otherwise flag for manual review | `test_messy_handwritten_dates` |
| 8 | Failure log contained people's names | Logging convenience | Log only form id, field and reason | `test_unparseable_dob_is_flagged_without_personal_data` |
