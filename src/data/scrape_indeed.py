"""Suggest Phoenix annotation labels from the provided Indeed CSV export."""

import argparse
import csv
import io
import re
from contextlib import contextmanager
from html import unescape
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit


DRIVE_FOLDER = "https://drive.google.com/drive/folders/1iGJ511t7Enpj9ShRZmMOkOH0FvRjpSut"
DRIVE_API = "https://www.googleapis.com/drive/v3/files"
INDEED_FILENAME = "indeed_job_listings.csv"


LABEL_PATTERNS = {
    "education_required": re.compile(
        r"\b(?:(?:high[ -]school|HS)\s+(?:diploma|education|degree|graduate)|high school or equivalent|"
        r"G\.?E\.?D\.?|(?:college|medical) degree|juris doctor|graduate of\b.{0,45}\bprogram|"
        r"(?-i:BS/MS|B\.?S\.?|M\.?S\.?|B\.?A\.?|B\.?E\.?|B\.?Tech\.?)(?=\s*/\s*B\.?E\.?|\s+[Ii]n\b)|"
        r"bachelors?\s+in\b|undergraduate degree|"
        r"(?:associate|bachelor|master)(?:['’]s|s)?\s+degree|bachelor(?:['’]s|s)?\s+or\s+master(?:['’]s|s)?\s+degree|"
        r"(?:bachelor|master)(?:['’]s|s)?\s+in\b|associate['’]s\s+in\b|"
        r"(?:bachelor|master)(?:['’]s|s)?(?=\s*(?:required|preferred|$))|"
        r"(?:undergraduate|graduate|doctoral) degree|degree\s+or\s+equivalent|doctorate|Ph\.?D\.?|"
        r"Medical Doctor|Doctor of Osteopathy|M\.?D\.?\s+or\s+D\.?O\.?)\b",
        re.IGNORECASE,
    ),
    "experience_required": re.compile(r"\b(?:experience|residency training)\b", re.IGNORECASE),
    "certification_required": re.compile(
        r"\b(?:certifications?|certificates?|licen[sc]es?|licensed|"
        r"board[ -]certified|CDL|licensure|state bar membership|membership in (?:any|a) state bar|"
        r"(?:active|current) DEA|(?:CPR|BLS|ACLS)\s+certified)\b", re.IGNORECASE,
    ),
}
REQUIRED = re.compile(
    r"\b(?:requires|required|requirements?|must(?:\s+have)?|minimum|mandatory|prerequisite)\b", re.I
)
OPTIONAL = re.compile(
    r"\b(?:preferred|a plus|nice to have|desired|optional|"
    r"(?:is |are )?not (?:required|necessary|needed)|"
    r"no\s+(?:[\w’-]+\s+){0,5}(?:experience|degree|license|certification)"
    r"(?:\s+(?:(?:is|are)\s+)?(?:required|necessary|needed))?)\b",
    re.I,
)
AMBIGUOUS = re.compile(
    r"\b(?:or|and/or|equivalent|within\s+\d+|upon hire|after hire|or\s+related)\b", re.I
)
EXPLICIT_CREDENTIAL = re.compile(r"\b(?:active|valid|current|unrestricted)\b", re.I)
LICENSE_CLAUSE = re.compile(r"\b(?:active|valid|current|unrestricted)\s+(?:[\w’'-]+\s+){0,5}(?:licen[sc]e|state bar)\b", re.I)
PREFERENCE = re.compile(r"\b(?:preferred|a (?:strong )?plus|a bonus|nice to have|desired|ideally|encouraged|we prefer)\b", re.I)
OPTIONAL_PREFIX = re.compile(r"^(?:preferred to have|bonus(?: points)?\b|no\b.{0,45}\bexperience\b)", re.I)
PREFERENCE_DETAIL = re.compile(r"[,;(]\s*(?:preferably|ideally)\b.*$", re.I)
DEGREE_SUBSTITUTION = re.compile(
    r"\bor\s+equivalent\s+(?:work\s+)?experience\b|\bwithout\s+(?:an?\s+)?(?:bachelor|master|college|degree)"
    r"|\bor\s+equivalent combination of education and experience\b|\bin lieu of (?:a |the )?degree\b|"
    r"\bor\s+(?:at least\s+)?\d+\+?\s+years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience\b(?![^.]*\bdegree\b)", re.I
)
NON_APPLICANT = re.compile(
    r"\b(?:compensation|salar(?:y|ies)|hourly rate|(?:rate|pay) range|pay rates?|pay within the range|base pay)\b.{0,160}"
    r"\b(?:determined|based|commensurate|var(?:y|ies)|depends?|considers|including)\b|"
    r"\b(?:foreign transcripts|application materials|certificates? of conformance|smog certificate|agency certification|"
    r"great place to work|(?:we|company) (?:are|is) .*certified|conducts employee trainings)\b", re.I
)
NON_REQUIRED_CONTEXT = re.compile(
    r"\b(?:customer|member|guest|brand|dining|register|student|training|patient) experience\b|"
    r"\b(?:gain|develop|depending on|based on)\b.{0,45}\bexperience\b", re.I
)
ZERO_EXPERIENCE = re.compile(r"\b0\s*(?:to|[-–])\s*\d+\s+years?\b[^.;]*\bexperience\b", re.I)
PROVEN_EXPERIENCE = re.compile(r"\bproven (?:work )?experience\b", re.I)
EXPERIENCE_DURATION = re.compile(
    r"\b(?:[1-9]\d*|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"(?:\s*\(\d+\))?(?:\s*[-–]\s*\d+)?\s*\+?\s*(?:or more\s+)?"
    r"(?:years?|yrs?|months?)\b(?:.{0,95}\bexperience\b|.{0,35}\b(?:working|selling)\b)", re.I
)
SOFT_DURATION = re.compile(r"\b(?:typically|ideal candidate will have)\b", re.I)
EXPERIENCE_FIELD = re.compile(r"^experience:\s*[-:]*\s*[1-9]\d*(?:\s*[-–]\s*\d+)?\+?\s*(?:yrs?|years?|months?)(?=\b|[A-Z][a-z])", re.I)
EXPERIENCE_SUMMARY = re.compile(r"^[1-9]\d*\s+year\(s\):\s*\w", re.I)
EDUCATION_EQUIVALENT = re.compile(r"\b(?:high[ -]school|HS)\b.{0,40}\bor\s+(?:equivalent|G\.?E\.?D\.?)\b", re.I)
SAME_EDUCATION_ALTERNATIVE = re.compile(
    r"\b(?:diploma|degree)\s*(?:/|or)\s*(?:GED|general education degree|equivalent\s*$)", re.I
)
PHYSICIAN_DEGREES = re.compile(r"\b(?:Medical Doctor or Doctor of Osteopathy|MD or DO)\b", re.I)
QUALIFICATION_HEADER = re.compile(r"(?:[\w/]+\s+){0,3}qualifications(?:/requirements)?", re.I)
REQUIREMENT_HEADER = re.compile(
    r"(?:minimum|required|basic|non-negotiable)\s+(?:education|experience|skills|qualifications|requirements|credentials)"
    r"(?:\s+and\s+experience)?|(?:job|education|other|role|position)\s+requirements|requirements|required|"
    r"(?:education|experience|licen[cs]es?(?:\s*/\s*certifications?)?)\s+required|must have(?:\s*:\s*minimum requirements)?|"
    r"minimum qualifications education and experience|essential qualifications|education and/or experience required", re.I
)
OPTIONAL_HEADER = re.compile(
    r"(?:preferred|desired)\s+(?:qualifications|experience|education|skills(?: and experience)?)|"
    r"(?:education|experience|licen[cs]es?(?:\s*/\s*certifications?)?)\s+preferred|"
    r"preferred certifications(?: and experience)?|bonus", re.I
)
PROFILE_HEADER = re.compile(
    r"(?:education\s*(?:[/&]|and)\s*experience|education qualifications|experience qualifications|"
    r"qualifications and skills|skills and qualifications|what (?:you(?:['’]ll| will)? (?:bring|need|have)|"
    r"we (?:need to see|are looking for|['’]re looking for))|you have|essential skills|"
    r"educational background|education|case manager requirements|professional qualifications|"
    r"required certifications|licensure|what you bring to the table \(must have\)|"
    r"here['’]s what you['’]ll need)", re.I
)
OTHER_HEADER = re.compile(
    r"(?:about(?: us| the role)?|responsibilities|duties|benefits|"
    r"compensation|schedule|what we offer|job description|work location|job type|pay|"
    r"position responsibilities|logistics|how to apply|compensation and benefits|"
    r"what you(?:['’]ll| will) (?:do|get)|what we offer|physical requirements|required training|"
    r"about the (?:role|team|company)|salary(?: range)?)", re.I
)
HTML_TAG = re.compile(r"</?[a-z][^<>]*>", re.I)
HTML_BREAK = re.compile(r"<\s*(?:br\b[^>]*|/(?:p|div|li|h[1-6]|ul|ol)\s*)>", re.I)
MONEY = r"\$\s*(?P<{0}>\d[\d,]*(?:\.\d+)?)\s*(?P<{0}_k>[kK])?"
PAY = re.compile(
    rf"\s*(?P<prefix>from\s+|up to\s+)?{MONEY.format('low')}"
    rf"(?:\s*(?:[-–—]|\bto\b)\s*{MONEY.format('high')})?"
    r"\s*(?:/\s*|per\s+|an?\s+)?(?P<unit>h|hr|hrs|hours?|hourly|years?|yr|yrs|annual(?:ly)?)"
    r"\s*", re.I,
)


def description_segments(description):
    """Yield source text and section context, dropping HTML markup if present."""
    plain = unescape(HTML_TAG.sub("", HTML_BREAK.sub("\n", description)))
    section = ""
    # The export often flattens separate bullets into runs of spaces.
    for line in re.split(r"\r?\n|[ \t]{2,}|\*{2,}|(?<=[.!?;])(?=[A-Z][a-z])|"
                         r"(?<=[a-z/])(?=(?:Education|Experience|Licensure|Location|Schedule|Benefits):)|"
                         r"(?<=preferred )(?=Experience:)|(?<=\s)(?=Required Qualifications:)|"
                         r"(?<=\s)(?=(?:Years of experience|Background requirements|Other requirements|Job Requirements|Education|Licensure|Schedule|Educational Background):)|"
                         r"(?<=[a-z])(?=No (?:prior |previous )?\w[^.]{0,35}experience)|"
                         r"(?<=[a-z])(?=(?:Requirements|Qualifications|Compensation|Benefits)\b)", plain):
        line = line.strip(" \t•*-–")
        experience_field = EXPERIENCE_FIELD.search(line)
        heading, colon, remainder = line.partition(":")
        if REQUIREMENT_HEADER.fullmatch(heading.strip()):
            section = "required"
        elif OPTIONAL_HEADER.fullmatch(heading.strip()) or heading.casefold() == "ideally, you’ll also have":
            section = "optional"
        elif QUALIFICATION_HEADER.fullmatch(heading.strip()) or PROFILE_HEADER.fullmatch(heading.strip()):
            section = "qualifications"
        elif OTHER_HEADER.fullmatch(heading.strip()):
            section = ""
        elif colon and not remainder.strip():
            section = ""
        else:
            remainder = line
        if experience_field:
            remainder = line
        if not colon and not remainder:
            continue
        for segment in re.split(r"(?<!\b[A-Z]\.)(?<=[.!?;])\s+|\s*[•●▪]\s*", remainder):
            if segment.strip():
                yield segment.strip(), section


def suggest_labels(description):
    segments = list(description_segments(description))
    result = {}
    for label, pattern in LABEL_PATTERNS.items():
        positive, negative, uncertain = [], [], []
        degree_waiver = label == "education_required" and any(
            DEGREE_SUBSTITUTION.search(segment) and (pattern.search(segment) or "degree" in segment.casefold())
            for segment, section in segments if section != "optional"
        )
        for segment, section in segments:
            candidate_text = NON_REQUIRED_CONTEXT.sub("", segment) if label == "experience_required" else segment
            experience_summary = label == "experience_required" and section == "required" and EXPERIENCE_SUMMARY.search(candidate_text)
            if not experience_summary and not pattern.search(candidate_text):
                continue
            license_clause = LICENSE_CLAUSE.search(segment) if label == "certification_required" else None
            if NON_APPLICANT.search(segment) and not license_clause:
                continue
            candidate_text = PREFERENCE_DETAIL.sub("", candidate_text)
            same_school_level = label == "education_required" and EDUCATION_EQUIVALENT.search(candidate_text)
            if same_school_level and section in {"required", "qualifications"} and re.search(
                r",\s*(?:BA|BS|bachelor|master)", candidate_text, re.I
            ):
                # Evaluate the high-school criterion separately from a preferred higher degree.
                candidate_text = candidate_text.split(",", 1)[0]
            if license_clause and section in {"required", "qualifications"}:
                trailing_text = segment[license_clause.end():]
                if not re.match(r"\s*(?:is\s+)?(?:preferred|optional|not required|or\b)", trailing_text, re.I):
                    candidate_text = segment[:license_clause.end()]
            if label == "education_required" and degree_waiver and not re.search(
                r"\b(?:high[ -]school|HS diploma|G\.?E\.?D\.?)\b", candidate_text, re.I
            ):
                negative.append(segment)
                continue
            if label == "certification_required" and re.search(r"board certified\s*(?:/|or)\s*board eligible", segment, re.I):
                negative.append(segment)
                continue
            optional_match = OPTIONAL.search(candidate_text)
            # Mask "not required" before looking for an independent requirement cue.
            explicitly_required = REQUIRED.search(OPTIONAL.sub("", candidate_text))
            if (label == "experience_required" and ZERO_EXPERIENCE.search(candidate_text)) or OPTIONAL_PREFIX.search(candidate_text) or (
                (section == "optional" or PREFERENCE.search(candidate_text)) and not explicitly_required
            ):
                negative.append(segment)
                continue
            experience_duration = label == "experience_required" and (
                EXPERIENCE_DURATION.search(candidate_text) or EXPERIENCE_FIELD.search(candidate_text)
            )
            if experience_duration and SOFT_DURATION.search(candidate_text):
                uncertain.append(segment)
                continue
            credential = label == "certification_required" and EXPLICIT_CREDENTIAL.search(candidate_text)
            if not optional_match and (experience_duration or credential):
                positive.append(segment)
                continue
            same_education = same_school_level or (label == "education_required" and (
                SAME_EDUCATION_ALTERNATIVE.search(segment) or PHYSICIAN_DEGREES.search(segment)
            ))
            if AMBIGUOUS.search(segment) and not same_education:
                matches_other_label = any(
                    other_label != label and candidate.search(segment)
                    for other_label, candidate in LABEL_PATTERNS.items()
                )
                if (matches_other_label and not explicitly_required and section not in {"required", "qualifications"}) or not (
                    explicitly_required or section in {"required", "qualifications"}
                    or (label == "experience_required" and PROVEN_EXPERIENCE.search(segment))
                ):
                    uncertain.append(segment)
                    continue
            if optional_match or section == "optional":
                mixed_subjects = optional_match and sum(
                    bool(candidate.search(segment)) for candidate in LABEL_PATTERNS.values()
                ) > 1
                if explicitly_required or mixed_subjects:
                    uncertain.append(segment)
                else:
                    negative.append(segment)
            elif explicitly_required or section in {"required", "qualifications"} or (
                label == "experience_required" and PROVEN_EXPERIENCE.search(segment)
            ):
                positive.append(segment)
            else:
                uncertain.append(segment)

        if positive:
            suggestion = "1"
        elif uncertain or not segments:
            suggestion = "review"
        else:
            suggestion = "0"
        result[f"{label}_suggested"] = suggestion
        result[f"{label}_evidence"] = " | ".join(dict.fromkeys(positive + negative + uncertain))
    return result


def annual_pay(text):
    """Normalize explicitly hourly or annual pay; keep unknown bounds blank."""
    match = PAY.fullmatch(text)
    if not match:
        return "", ""

    def amount(bound):
        number = match[bound]
        if number is None:
            return None
        value = float(number.replace(",", ""))
        return value * 1000 if match[f"{bound}_k"] else value

    low, high = amount("low"), amount("high")
    if low <= 0 or (high is not None and (high < low or match["prefix"])):
        return "", ""
    factor = 2080 if match["unit"].lower().startswith("h") else 1
    if match["prefix"] and match["prefix"].lower().startswith("up"):
        return "", round(low * factor, 2)
    if high is None and not match["prefix"]:
        high = low
    return round(low * factor, 2), "" if high is None else round(high * factor, 2)


@contextmanager
def open_drive_csv(folder_id, encoding):
    try:
        import google.auth
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import AuthorizedSession
        from requests.exceptions import RequestException
    except ImportError as error:
        raise ValueError('Drive input requires python -m pip install "google-auth[requests]".') from error

    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        with AuthorizedSession(credentials) as session:
            params = {
                "q": f"'{folder_id}' in parents and name = '{INDEED_FILENAME}' and trashed = false",
                "fields": "nextPageToken,files(id,capabilities(canDownload))",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            matches = []
            while True:
                with session.get(DRIVE_API, params=params, timeout=30) as response:
                    response.raise_for_status()
                    page = response.json()
                matches.extend(page.get("files", []))
                if not page.get("nextPageToken"):
                    break
                params["pageToken"] = page["nextPageToken"]
            if len(matches) != 1:
                raise ValueError(f"Expected one {INDEED_FILENAME} in the Drive folder, found {len(matches)}.")
            file = matches[0]
            if file.get("capabilities", {}).get("canDownload") is False:
                raise ValueError(f"Drive credentials lack download access to {INDEED_FILENAME}.")
            with session.get(
                f"{DRIVE_API}/{file['id']}",
                params={"alt": "media", "supportsAllDrives": "true"},
                stream=True,
                timeout=60,
            ) as response:
                response.raise_for_status()
                response.raw.decode_content = True
                with io.TextIOWrapper(response.raw, encoding=encoding, newline="") as source:
                    yield source
    except (GoogleAuthError, RequestException) as error:
        raise ValueError(f"Google Drive request failed: {error}") from error


def open_csv(input_source, output_path, encoding):
    if isinstance(input_source, str) and input_source.startswith(("https://", "http://")):
        url = urlsplit(input_source)
        folder = re.fullmatch(r"/drive/(?:u/\d+/)?folders/([\w-]+)/?", url.path)
        if url.scheme != "https" or url.netloc != "drive.google.com" or not folder:
            raise ValueError("Use a Google Drive folder URL or a local CSV path.")
        return open_drive_csv(folder[1], encoding)

    input_path = Path(input_source)
    if input_path.is_dir():
        input_path /= INDEED_FILENAME
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Specify a different output path to preserve the source CSV.")
    return input_path.open(encoding=encoding, newline="")


def label_csv(input_path, output_path, description_column, encoding, deduplicate, limit=None):
    csv.field_size_limit(16 * 1024 * 1024)
    seen = set()
    written = skipped = 0
    temporary_path = None
    group_columns = ("job_title", "company_name", "location")
    output_columns = ["annual_pay_low", "annual_pay_high", "duplicate_group"]
    output_columns.extend(suggest_labels(""))

    try:
        with open_csv(input_path, output_path, encoding) as source:
            reader = csv.DictReader(source)
            headers = reader.fieldnames or []
            if description_column not in headers:
                raise ValueError(f"Missing description column {description_column!r}. Found: {headers}")
            if len(set(headers)) != len(headers) or set(headers).intersection(output_columns):
                raise ValueError("The source has duplicate headers or existing generated columns.")
            if deduplicate and not set(group_columns).issubset(headers):
                raise ValueError(f"Deduplication requires these columns: {', '.join(group_columns)}")
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=output_path.parent, delete=False
            ) as target:
                temporary_path = Path(target.name)
                writer = csv.DictWriter(target, fieldnames=headers + output_columns)
                writer.writeheader()
                for row in reader:
                    if None in row or None in row.values():
                        raise ValueError(f"Unexpected column count at CSV line {reader.line_num}.")
                    group = tuple(" ".join(row.get(col, "").casefold().split()) for col in group_columns)
                    if deduplicate and all(group):
                        if group in seen:
                            skipped += 1
                            continue
                        seen.add(group)
                    row["duplicate_group"] = repr(group) if all(group) else ""
                    row["annual_pay_low"], row["annual_pay_high"] = annual_pay(row.get("salary_formatted", ""))
                    row.update(suggest_labels(row[description_column]))
                    writer.writerow(row)
                    written += 1
                    if written == limit:
                        break
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return written, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", nargs="?", default=DRIVE_FOLDER,
                        help="Local CSV, local directory, or Drive folder URL (defaults to the Phoenix folder)")
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--description-column", default="description_text")
    parser.add_argument("--encoding", default="utf-8-sig", help="Input CSV encoding")
    parser.add_argument("--deduplicate", action="store_true", help="Keep the first row per title/company/location")
    parser.add_argument("--limit", type=int, help="Stop after writing this many postings")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        written, skipped = label_csv(
            args.input_csv, args.output_csv, args.description_column, args.encoding, args.deduplicate, args.limit
        )
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"Wrote {written:,} postings to {args.output_csv} ({skipped:,} duplicate rows skipped).")


if __name__ == "__main__":
    main()
