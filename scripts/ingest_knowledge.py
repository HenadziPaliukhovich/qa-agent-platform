#!/usr/bin/env python3
import argparse, json, sys, urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8005/api/knowledge/documents"
EXT_TO_DOC_TYPE = {
    ".md": "markdown", ".txt": "text",
    ".json": "json", ".yaml": "openapi",
    ".yml": "openapi", ".openapi": "openapi",
}

def infer_doc_type(path, explicit):
    if explicit:
        return explicit
    return EXT_TO_DOC_TYPE.get(path.suffix.lower(), "general")

def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into QA RAG knowledge base")
    parser.add_argument("paths", nargs="+", help="Files to ingest")
    parser.add_argument("--project-id", default="default-project")
    parser.add_argument("--service-name", default=None)
    parser.add_argument("--doc-type", default=None)
    parser.add_argument("--source", default="cli")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    code = 0
    for raw in args.paths:
        p = Path(raw)
        if not p.is_file():
            print(f"[skip] not found: {p}", file=sys.stderr); code = 1; continue
        try:
            result = post_json(args.url, {
                "project_id": args.project_id,
                "service_name": args.service_name,
                "title": p.name,
                "doc_type": infer_doc_type(p, args.doc_type),
                "source": args.source,
                "tags": args.tag,
                "content": p.read_text(encoding="utf-8"),
            })
            print(json.dumps({"file": str(p), **result}, ensure_ascii=False))
        except Exception as e:
            print(f"[error] {p}: {e}", file=sys.stderr); code = 1
    return code

if __name__ == "__main__":
    raise SystemExit(main())
