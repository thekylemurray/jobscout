# JobScout for Windows

This preview adds a native window and separate search profiles to JobScout. Each person can use the same executable with their own preferences. No terminal or Python installation is needed on the recipient's computer.

## Getting started

1. Download the `JobScout-Windows` artifact from a successful **Windows desktop** run in GitHub Actions. Extract the ZIP.
2. Open `JobScout.exe`.
3. Choose **Import profile** and select the supplied JSON file. This copies preferences into a separate local profile; there is no code to edit. Alternatively, fill out the Search preferences form and Save.
4. Review **Job sources**. Only the configured, enabled feeds are searched. Add or remove sources using the form. Workday needs the employer's full careers board URL; Greenhouse and Lever use a board token.
5. Select **Search configured sources**. Large boards can take several minutes. Keep the app open until it finishes.
6. Review source health, then **Open results**. Check **View scan log** if a feed failed. No matches from failed feeds does not mean those employers have no vacancies.
7. Use **Check a posting** to paste a job found on LinkedIn, a company website, or elsewhere. Enter the location and work arrangement as advertised. The result opens in your browser.

Use **Open saved profile** to reopen a profile on a later visit. Profiles are stored in `%LOCALAPPDATA%\JobScout\profiles`, each with its own search history and reports. **New profile** starts a separate search. Importing an existing profile again creates another copy. Save before switching profiles. Personal profiles and résumés are not bundled into the executable or public repository.

## What the preview can and cannot establish

- The portable matcher uses target title phrases and skill terms with explicit explanations. Scores are heuristic review aids, not calibrated percentages or hiring probabilities. Title phrases match in their written order: include alternate formulations where needed.
- Local cities and explicit remote metadata control eligibility. Hybrid roles outside the configured cities are excluded. Remote roles require a human check of country/state restrictions and required office visits. Ambiguous location metadata may miss eligible roles; use manual review.
- An explicit annual USD salary range wholly below the minimum is excluded. Missing currency, missing pay period, bonuses, stock, and other ambiguous compensation remain unverified. Salary is not always available in feed metadata. Paste it in manual review when needed.
- Qualification terms are flagged for review. The app does not reliably distinguish a mandatory doctorate from a preferred doctorate or an equivalent experience alternative. It does not certify degree eligibility, health insurance, industry, or work-life balance.
- Employer preferences are displayed as evidence, not automatic eligibility. Industry terms missing from a description trigger a review note.
- Source coverage is limited to configured feeds; this is not a full LinkedIn/Indeed search. It does not log in or submit applications.
- Keyword rules can miss relevant jobs or retain irrelevant ones. Review the posting itself, plus rejection audits and source logs.

## Building and testing

The Windows desktop workflow builds on Windows because PyInstaller packages are OS-specific. It runs the regression suite, exercises the native form, packages a windowed executable, and checks that the executable opens a window. Artifacts contain the executable and this guide only. They expire after 30 days; this is a preview distribution, not an auto-updating installer.

Developers can run `python -m jobscout.desktop`. The GUI needs Tk, included with standard Windows Python distributions. CI uses Python 3.12 and a pinned PyInstaller build dependency. The app has no additional runtime Python dependencies.

The executable is not code-signed. Windows may display an unknown-publisher warning. Distribute only an artifact from the expected repository and successful build; do not ask recipients to disable security software.

Reference: https://pyinstaller.org/en/stable/operating-mode.html

## Version 1.1 search improvements

- Searches up to three employer boards concurrently and displays listing progress.
- Workday sources may specify `search_text` to narrow retrieval at the employer endpoint. The scan report records that query, listing counts, title candidates, and detail failures. Query-limited retrieval is not exhaustive employer coverage.
- **Scan report / exclusions** opens a readable report even if no jobs match, showing locations, work arrangements, and rejection reasons.
- Head-of-function titles can be reviewed as possible Director equivalents; the app flags the scope for confirmation. Punctuation between title words no longer causes a missed match.
- Qualification flags include a short excerpt so required specialties or degrees are easier to inspect.
- Personal profile updates are supplied separately. Import the new profile file; replacing the executable alone does not change saved sources or preferences.
