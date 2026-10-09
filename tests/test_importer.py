from engine import importer


def test_tokens_in_finds_boards():
    html = '<a href="https://jobs.ashbyhq.com/attio/abc">Jobs</a> <iframe src="https://boards.greenhouse.io/embed/job_board?for=lattice">'
    assert ("ashby", "attio") in importer.tokens_in(html)
    assert ("greenhouse", "lattice") in importer.tokens_in(html)
    assert all(t not in importer.SKIP_TOKENS for _, t in importer.tokens_in(html))


def test_resolve_prefers_link_then_guesses():
    pages = {"https://acme.io/careers": '<a href="https://jobs.lever.co/acme-inc">'}
    hit = importer.resolve_ats("acme.io", "Acme Inc", fetch=lambda u: pages.get(u, ""), probe=lambda a, t: t == "acme-inc")
    assert hit == ("lever", "acme-inc")
    hit2 = importer.resolve_ats("acme.io", "Acme", fetch=lambda u: "", probe=lambda a, t: (a, t) == ("ashby", "acme"))
    assert hit2 == ("ashby", "acme")
    assert importer.resolve_ats("acme.io", "Acme", fetch=lambda u: "", probe=lambda a, t: False) is None


def test_import_csv_merges_and_keeps_hand_edits(tmp_path):
    csv_path = tmp_path / "leads.csv"
    csv_path.write_text("Company,Domain,Size\nAcme,https://www.acme.io/,120\nBeta,beta.co,\n")
    acc = tmp_path / "accounts.yaml"
    acc.write_text("accounts:\n  - {company: Acme, domain: acme.io, country: US}\n")
    r = importer.import_csv(str(csv_path), acc, fetch=lambda u: "", probe=lambda a, t: t == "acme", log=lambda *_: None)
    assert r == {"added": 1, "updated": 1, "resolved": 1, "unresolved": ["beta.co"], "total": 2}
    import yaml
    rows = yaml.safe_load(acc.read_text())["accounts"]
    acme = next(x for x in rows if x["domain"] == "acme.io")
    assert acme["country"] == "US" and acme["size"] == 120 and acme["ats"] in ("greenhouse", "lever", "ashby") and acme["token"] == "acme"
