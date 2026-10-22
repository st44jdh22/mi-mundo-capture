"""Generate the small native Xcode project using only Python's standard library."""
from pathlib import Path
import hashlib

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

sources = ['LocalCapture.swift', 'HeySophieApp.swift', 'MediaCapture.swift']
for path in sources + ['CaptureDiskTests.swift']:
    add('file:'+path, 'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = '+quote(path)+'; sourceTree = "<group>";')
    add('build:'+path, 'isa = PBXBuildFile; fileRef = '+ident('file:'+path)+';')
add('plist', 'isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>";')
add('appProduct', 'isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = HeySophie.app; sourceTree = BUILT_PRODUCTS_DIR;')
add('testProduct', 'isa = PBXFileReference; explicitFileType = wrapper.cfbundle; includeInIndex = 0; path = HeySophieTests.xctest; sourceTree = BUILT_PRODUCTS_DIR;')
add('appGroup', 'isa = PBXGroup; children = '+refs(['file:'+s for s in sources]+['plist'])+'; path = HeySophie; sourceTree = "<group>";')
add('testGroup', 'isa = PBXGroup; children = '+refs(['file:CaptureDiskTests.swift'])+'; path = HeySophieTests; sourceTree = "<group>";')
add('products', 'isa = PBXGroup; children = '+refs(['appProduct','testProduct'])+'; name = Products; sourceTree = "<group>";')
add('rootGroup', 'isa = PBXGroup; children = '+refs(['appGroup','testGroup','products'])+'; sourceTree = "<group>";')
for target, files in [('app', sources), ('test', ['CaptureDiskTests.swift'])]:
    add(target+'Sources', 'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = '+refs(['build:'+s for s in files])+'; runOnlyForDeploymentPostprocessing = 0;')
    for phase, isa in [('Frameworks','PBXFrameworksBuildPhase'),('Resources','PBXResourcesBuildPhase')]:
        add(target+phase, 'isa = '+isa+'; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;')
add('proxy', 'isa = PBXContainerItemProxy; containerPortal = '+ident('project')+'; proxyType = 1; remoteGlobalIDString = '+ident('appTarget')+'; remoteInfo = HeySophie;')
add('testDependency', 'isa = PBXTargetDependency; target = '+ident('appTarget')+'; targetProxy = '+ident('proxy')+';')
for scope in ['project','app','test']:
    for mode in ['Debug','Release']:
        settings = {'SWIFT_VERSION':'5.0', 'IPHONEOS_DEPLOYMENT_TARGET':'17.0', 'SDKROOT':'iphoneos', 'TARGETED_DEVICE_FAMILY':'1', 'CLANG_ENABLE_MODULES':'YES', 'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if mode=='Debug' else '-O'}
        if scope != 'project':
            settings.update(PRODUCT_NAME='$(TARGET_NAME)', PRODUCT_BUNDLE_IDENTIFIER='app.heysophie.capture' if scope=='app' else 'app.heysophie.capture.tests', CODE_SIGN_STYLE='Automatic', GENERATE_INFOPLIST_FILE='NO' if scope=='app' else 'YES')
            if scope=='app':
                settings.update(INFOPLIST_FILE='HeySophie/Info.plist', MARKETING_VERSION='0.1', CURRENT_PROJECT_VERSION='1', ENABLE_TESTABILITY='YES' if mode=='Debug' else 'NO')
            else:
                settings.update(TEST_HOST='$(BUILT_PRODUCTS_DIR)/HeySophie.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/HeySophie', BUNDLE_LOADER='$(TEST_HOST)')
                # iOS app executable is at bundle root.
                settings['TEST_HOST']='$(BUILT_PRODUCTS_DIR)/HeySophie.app/HeySophie'
        add(scope+mode, 'isa = XCBuildConfiguration; buildSettings = { '+' '.join(k+' = '+quote(v)+';' for k,v in sorted(settings.items()))+' }; name = '+mode+';')
    add(scope+'Configs', 'isa = XCConfigurationList; buildConfigurations = '+refs([scope+'Debug',scope+'Release'])+'; defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
for scope, name, product in [('app','HeySophie','appProduct'),('test','HeySophieTests','testProduct')]:
    add(scope+'Target', 'isa = PBXNativeTarget; buildConfigurationList = '+ident(scope+'Configs')+'; buildPhases = '+refs([scope+'Sources',scope+'Frameworks',scope+'Resources'])+'; buildRules = (); dependencies = '+(refs(['testDependency']) if scope=='test' else '()')+'; name = '+name+'; productName = '+name+'; productReference = '+ident(product)+'; productType = '+quote('com.apple.product-type.application' if scope=='app' else 'com.apple.product-type.bundle.unit-test')+';')
add('project', 'isa = PBXProject; attributes = { LastUpgradeCheck = 1600; }; buildConfigurationList = '+ident('projectConfigs')+'; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en, Base,); mainGroup = '+ident('rootGroup')+'; productRefGroup = '+ident('products')+'; projectDirPath = ""; projectRoot = ""; targets = '+refs(['appTarget','testTarget'])+';')
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
