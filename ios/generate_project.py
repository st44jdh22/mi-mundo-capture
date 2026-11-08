"""Generate the small native Xcode project using only Python's standard library."""
from pathlib import Path
import hashlib
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--dat", action="store_true", help="Link pinned DAT 1.0.1 for simulator mock testing")
args = parser.parse_args()

base = Path(__file__).resolve().parent
objects = {}
def ident(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()
def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
def add(name, body):
    objects[ident(name)] = body
    return ident(name)
def refs(names):
    return '(' + ', '.join(ident(n) for n in names) + ',)'

sources = ['LocalCapture.swift', 'HeySophieApp.swift', 'MediaCapture.swift', 'PhotoCapture.swift', 'MetaPhotoCamera.swift', 'PhotoProofScreen.swift']
tests = ['CaptureDiskTests.swift', 'PhotoCaptureTests.swift', 'MetaCameraTests.swift']
resources = ['Fixtures/synthetic-photo.jpg', 'Fixtures/synthetic-preview.mp4']
packages = ['MWDATCore', 'MWDATCamera', 'MWDATMockDevice'] if args.dat else []
for name in packages:
    add('pkg:'+name, 'isa = XCSwiftPackageProductDependency; package = '+ident('datPackage')+'; productName = '+name+';')
    add('link:'+name, 'isa = PBXBuildFile; productRef = '+ident('pkg:'+name)+';')
if args.dat:
    add('datPackage', 'isa = XCRemoteSwiftPackageReference; repositoryURL = "https://github.com/facebook/meta-wearables-dat-ios"; requirement = { kind = exactVersion; version = 1.0.1; };')
for path in resources:
    add('resource:'+path, 'isa = PBXFileReference; lastKnownFileType = file; path = '+quote(path)+'; sourceTree = "<group>";')
    add('resbuild:'+path, 'isa = PBXBuildFile; fileRef = '+ident('resource:'+path)+';')
for path in sources + tests:
    add('file:'+path, 'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = '+quote(path)+'; sourceTree = "<group>";')
    add('build:'+path, 'isa = PBXBuildFile; fileRef = '+ident('file:'+path)+';')
add('plist', 'isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>";')
add('appProduct', 'isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = HeySophie.app; sourceTree = BUILT_PRODUCTS_DIR;')
add('testProduct', 'isa = PBXFileReference; explicitFileType = wrapper.cfbundle; includeInIndex = 0; path = HeySophieTests.xctest; sourceTree = BUILT_PRODUCTS_DIR;')
add('appGroup', 'isa = PBXGroup; children = '+refs(['file:'+s for s in sources]+['resource:'+s for s in resources]+['plist'])+'; path = HeySophie; sourceTree = "<group>";')
add('testGroup', 'isa = PBXGroup; children = '+refs(['file:'+s for s in tests])+'; path = HeySophieTests; sourceTree = "<group>";')
add('products', 'isa = PBXGroup; children = '+refs(['appProduct','testProduct'])+'; name = Products; sourceTree = "<group>";')
add('rootGroup', 'isa = PBXGroup; children = '+refs(['appGroup','testGroup','products'])+'; sourceTree = "<group>";')
for target, files in [('app', sources), ('test', tests)]:
    add(target+'Sources', 'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = '+refs(['build:'+s for s in files])+'; runOnlyForDeploymentPostprocessing = 0;')
    for phase, isa in [('Frameworks','PBXFrameworksBuildPhase'),('Resources','PBXResourcesBuildPhase')]:
        add(target+phase, 'isa = '+isa+'; buildActionMask = 2147483647; files = '+(refs(['link:'+n for n in packages]) if target=='app' and phase=='Frameworks' and packages else refs(['resbuild:'+n for n in resources]) if target=='app' and phase=='Resources' else '()')+'; runOnlyForDeploymentPostprocessing = 0;')
add('proxy', 'isa = PBXContainerItemProxy; containerPortal = '+ident('project')+'; proxyType = 1; remoteGlobalIDString = '+ident('appTarget')+'; remoteInfo = HeySophie;')
add('testDependency', 'isa = PBXTargetDependency; target = '+ident('appTarget')+'; targetProxy = '+ident('proxy')+';')
for scope in ['project','app','test']:
    for mode in ['Debug','Release']:
        settings = {'SWIFT_VERSION':'5.0', 'IPHONEOS_DEPLOYMENT_TARGET':'17.2', 'SDKROOT':'iphoneos', 'TARGETED_DEVICE_FAMILY':'1', 'CLANG_ENABLE_MODULES':'YES', 'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if mode=='Debug' else '-O'}
        if args.dat:
            settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = '$(inherited) HS_META_DAT'
        if scope != 'project':
            settings.update(PRODUCT_NAME='$(TARGET_NAME)', PRODUCT_BUNDLE_IDENTIFIER='app.heysophie.capture.photodev' if scope=='app' else 'app.heysophie.capture.photodev.tests', CODE_SIGN_STYLE='Automatic', GENERATE_INFOPLIST_FILE='NO' if scope=='app' else 'YES')
            if scope=='app':
                settings.update(INFOPLIST_FILE='HeySophie/Info-Meta.plist' if args.dat else 'HeySophie/Info.plist', MARKETING_VERSION='0.1', CURRENT_PROJECT_VERSION='1', ENABLE_TESTABILITY='YES' if mode=='Debug' else 'NO')
            else:
                settings.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/HeySophie.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/HeySophie', BUNDLE_LOADER='$(TEST_HOST)')
                # iOS app executable is at bundle root.
                settings['TEST_HOST']='$(BUILT_PRODUCTS_DIR)/HeySophie.app/HeySophie'
        add(scope+mode, 'isa = XCBuildConfiguration; buildSettings = { '+' '.join(k+' = '+quote(v)+';' for k,v in sorted(settings.items()))+' }; name = '+mode+';')
    add(scope+'Configs', 'isa = XCConfigurationList; buildConfigurations = '+refs([scope+'Debug',scope+'Release'])+'; defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
for scope, name, product in [('app','HeySophie','appProduct'),('test','HeySophieTests','testProduct')]:
    add(scope+'Target', 'isa = PBXNativeTarget; packageProductDependencies = '+(refs(['pkg:'+n for n in packages]) if scope=='app' and packages else '()')+'; buildConfigurationList = '+ident(scope+'Configs')+'; buildPhases = '+refs([scope+'Sources',scope+'Frameworks',scope+'Resources'])+'; buildRules = (); dependencies = '+(refs(['testDependency']) if scope=='test' else '()')+'; name = '+name+'; productName = '+name+'; productReference = '+ident(product)+'; productType = '+quote('com.apple.product-type.application' if scope=='app' else 'com.apple.product-type.bundle.unit-test')+';')
add('project', 'isa = PBXProject; packageReferences = '+(refs(['datPackage']) if args.dat else '()')+'; attributes = { LastUpgradeCheck = 1600; }; buildConfigurationList = '+ident('projectConfigs')+'; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en, Base,); mainGroup = '+ident('rootGroup')+'; productRefGroup = '+ident('products')+'; projectDirPath = ""; projectRoot = ""; targets = '+refs(['appTarget','testTarget'])+';')
project = base/'HeySophie.xcodeproj'
project.mkdir(exist_ok=True)
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n'+ '\n'.join(k+' = { '+v+' };' for k,v in objects.items())+'\n}; rootObject = '+ident('project')+'; }\n')
folder = project/'xcshareddata/xcschemes'
folder.mkdir(parents=True,exist_ok=True)
app_ref = f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{ident("appTarget")}" BuildableName="HeySophie.app" BlueprintName="HeySophie" ReferencedContainer="container:HeySophie.xcodeproj"/>'
test_ref = f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{ident("testTarget")}" BuildableName="HeySophieTests.xctest" BlueprintName="HeySophieTests" ReferencedContainer="container:HeySophie.xcodeproj"/>'
(folder/'HeySophie.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{app_ref}</BuildActionEntry><BuildActionEntry buildForTesting="YES" buildForRunning="NO" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="NO">{test_ref}</BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables><TestableReference skipped="NO">{test_ref}</TestableReference></Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{app_ref}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugServiceExtension="internal"><BuildableProductRunnable runnableDebuggingMode="0">{app_ref}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''')
print(f'Generated project with {len(objects)} objects and shared app/test scheme.')
