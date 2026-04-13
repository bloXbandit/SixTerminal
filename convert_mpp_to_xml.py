"""
convert_mpp_to_xml.py - Convert all .mpp files in copilot_web/projects/ to MS Project XML.
Run locally (requires Java + mpxj installed).
Output XMLs are saved alongside the MPPs with the same name but .xml extension.
"""
import os
import sys

def convert_all():
    projects_dir = os.path.join(os.path.dirname(__file__), "copilot_web", "projects")
    
    try:
        from mpxj import UniversalProjectReader
        from mpxj.writer import UniversalProjectWriter
    except ImportError:
        print("ERROR: mpxj not installed. Run: pip install mpxj JPype1")
        print("Also requires Java 11+ on PATH.")
        sys.exit(1)

    converted = 0
    failed = 0

    for slug in sorted(os.listdir(projects_dir)):
        project_path = os.path.join(projects_dir, slug)
        if not os.path.isdir(project_path):
            continue
        for fname in sorted(os.listdir(project_path)):
            if not fname.endswith(".mpp"):
                continue
            mpp_path = os.path.join(project_path, fname)
            xml_path = mpp_path.replace(".mpp", ".xml")
            if os.path.exists(xml_path):
                print(f"  SKIP (exists): {slug}/{fname}")
                continue
            try:
                reader = UniversalProjectReader()
                project = reader.read(mpp_path)
                writer = UniversalProjectWriter()
                writer.write(project, xml_path)
                print(f"  OK: {slug}/{fname} -> {os.path.basename(xml_path)}")
                converted += 1
            except Exception as e:
                print(f"  FAIL: {slug}/{fname} — {e}")
                failed += 1

    print(f"\nDone: {converted} converted, {failed} failed.")
    if converted > 0:
        print("\nNow run:")
        print("  git add copilot_web/projects")
        print("  git commit -m 'Add MS Project XML exports (no Java required on Render)'")
        print("  git push origin master")

if __name__ == "__main__":
    convert_all()
