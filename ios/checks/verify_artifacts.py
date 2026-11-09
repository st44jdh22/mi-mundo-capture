"""Host-side artifact checks. Does NOT compile Swift, run XCTest or emulate iOS."""
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image

IOS = Path(__file__).resolve().parents[1]

def check():
    fixture = IOS / 'HeySophie/Fixtures/synthetic-photo.jpg'
    metadata = json.loads(fixture.with_suffix('.json').read_text())
    data = fixture.read_bytes()
    assert hashlib.sha256(data).hexdigest() == metadata['sha256']
    assert len(data) == metadata['bytes']
    with Image.open(fixture) as image:
        image.load()
        assert image.format == 'JPEG'
        assert list(image.size) == [metadata['width'], metadata['height']]
        assert image.getpixel((0, 0)) != image.getpixel((31, 23))
    video = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height',
                            '-of', 'json', str(fixture.with_name('synthetic-preview.mp4'))],
                           capture_output=True, text=True, check=True)
    streams = json.loads(video.stdout)['streams']
    assert len(streams) == 1 and streams[0]['codec_type'] == 'video'
    for name in ['Info.plist', 'Info-Meta.plist']:
        plist = plistlib.loads((IOS / 'HeySophie' / name).read_bytes())
        assert plist['MWDAT']['Analytics']['OptOut'] is True
        assert plist['MWDAT']['CrashReporting']['OptOut'] is True
        assert 'UIBackgroundModes' not in plist
    meta = plistlib.loads((IOS / 'HeySophie/Info-Meta.plist').read_bytes())
    for name in ['NSMicrophoneUsageDescription', 'NSCameraUsageDescription', 'NSPhotoLibraryUsageDescription',
                 'NSLocalNetworkUsageDescription', 'NSBluetoothAlwaysUsageDescription']:
        assert name not in meta  # simulator mock only, physical transport config deliberately held
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'ios'
        shutil.copytree(IOS, target)
        for dat in [False, True]:
            args = ['python3', str(target / 'generate_project.py')] + (['--dat'] if dat else [])
            subprocess.run(args, capture_output=True, check=True)
            project = target / 'HeySophie.xcodeproj/project.pbxproj'
            first = project.read_bytes()
            subprocess.run(args, capture_output=True, check=True)
            assert first == project.read_bytes(), 'Project generation not deterministic'
            text = first.decode()
            defined = set(re.findall(r'^([0-9A-F]{24}) = ', text, re.M))
            referenced = set(re.findall(r'\b[0-9A-F]{24}\b', text))
            assert referenced <= defined, 'Dangling Xcode object reference'
            for path in re.findall(r'lastKnownFileType = sourcecode.swift; path = "([^"]+)"', text):
                assert (target / 'HeySophie' / path).exists() or (target / 'HeySophieTests' / path).exists()
            for path in re.findall(r'lastKnownFileType = file; path = "([^"]+)"', text):
                assert (target / 'HeySophie' / path).exists()
            if dat:
                assert 'kind = exactVersion; version = 1.0.1;' in text
                assert 'HS_META_DAT' in text and 'Info-Meta.plist' in text
                for product in ['MWDATCore', 'MWDATCamera', 'MWDATMockDevice']:
                    assert f'productName = {product};' in text
            else:
                assert 'XCRemoteSwiftPackageReference' not in text
                assert 'HS_META_DAT' not in text
            scheme = ET.parse(target / 'HeySophie.xcodeproj/xcshareddata/xcschemes/HeySophie.xcscheme')
            for ref in scheme.iter('BuildableReference'):
                assert ref.attrib['BlueprintIdentifier'] in defined
    print('PASS: fixture JPEG decode/content/size/hash, silent preview video, both privacy plists,')
    print('      deterministic offline/DAT project graphs, resource/source references and shared scheme.')
    print('NOT RUN: Swift compilation, XCTest, iOS simulator, official SDK mock or real glasses.')
    print(json.dumps(metadata, sort_keys=True))

if __name__ == '__main__':
    check()
