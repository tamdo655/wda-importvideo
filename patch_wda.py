#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Va WebDriverAgent:
- POST /wda/importVideo  : ghi video THANG vao Thu vien anh (PHPhotoLibrary),
  tu bam "Allow" ngay tren luong handler (FBAlert) -> khong cham phone.
- GET  /wda/vpnStatus    : doc thanh trang thai, tra {"vpn": true/false} neu co
  bieu tuong VPN -> de tool theo doi rot VPN.

PHIEN BAN 5 (29/06/2026).
"""
import os
import sys

TARGET = os.path.join("WebDriverAgentLib", "Commands", "FBCustomCommands.m")

IMPORT_ANCHOR = '#import "FBCustomCommands.h"'
IMPORT_ADD = ('#import "FBCustomCommands.h"\n'
              '#import "FBAlert.h"  // [patch] auto-accept Photos alert\n'
              '@import Photos;  // [patch] importVideo -> PHPhotoLibrary')

ROUTE_ANCHOR = ('[[FBRoute OPTIONS:@"/*"].withoutSession respondWithTarget:self '
                'action:@selector(handlePingCommand:)],')
ROUTE_ADD = (
    '    [[FBRoute POST:@"/wda/importVideo"].withoutSession '
    'respondWithTarget:self action:@selector(handleImportVideo:)],\n'
    '    [[FBRoute POST:@"/wda/importVideo"] '
    'respondWithTarget:self action:@selector(handleImportVideo:)],\n'
    '    [[FBRoute POST:@"/wda/deleteRecentVideos"].withoutSession '
    'respondWithTarget:self action:@selector(handleDeleteRecentVideos:)],\n'
    '    [[FBRoute POST:@"/wda/deleteRecentVideos"] '
    'respondWithTarget:self action:@selector(handleDeleteRecentVideos:)],\n'
    '    [[FBRoute GET:@"/wda/vpnStatus"].withoutSession '
    'respondWithTarget:self action:@selector(handleVpnStatus:)],\n'
    '    [[FBRoute GET:@"/wda/vpnStatus"] '
    'respondWithTarget:self action:@selector(handleVpnStatus:)],\n'
    '    ' + ROUTE_ANCHOR
)

HANDLER = r'''
#pragma mark - [patch] vpnStatus

// [patch] Tra {"vpn": true} neu thanh trang thai co bieu tuong/chu "VPN".
+ (id<FBResponsePayload>)handleVpnStatus:(FBRouteRequest *)request
{
  BOOL vpnOn = NO;
  NSMutableArray *seen = [NSMutableArray array];
  @try {
    NSMutableArray<XCUIApplication *> *apps = [NSMutableArray array];
    XCUIApplication *act = XCUIApplication.fb_activeApplication;
    if (nil != act) { [apps addObject:act]; }
    XCUIApplication *sys = XCUIApplication.fb_systemApplication;
    if (nil != sys && sys != act) { [apps addObject:sys]; }
    for (XCUIApplication *app in apps) {
      XCUIElementQuery *bars = app.statusBars;
      NSUInteger nb = bars.count;
      for (NSUInteger i = 0; i < nb; i++) {
        XCUIElement *bar = [bars elementBoundByIndex:i];
        NSArray<XCUIElement *> *kids =
          [[bar descendantsMatchingType:XCUIElementTypeAny] allElementsBoundByIndex];
        for (XCUIElement *k in kids) {
          NSString *lbl = k.label ?: @"";
          NSString *idf = k.identifier ?: @"";
          id vv = k.value;
          NSString *val = [vv isKindOfClass:NSString.class] ? (NSString *)vv : @"";
          if (seen.count < 40) {
            [seen addObject:[NSString stringWithFormat:@"%@|%@|%@", lbl, idf, val]];
          }
          NSString *all = [NSString stringWithFormat:@"%@ %@ %@", lbl, idf, val];
          if ([all rangeOfString:@"VPN" options:NSCaseInsensitiveSearch].location != NSNotFound) {
            vpnOn = YES;
          }
        }
      }
    }
  } @catch (__unused NSException *ex) {
  }
  return FBResponseWithObject(@{@"vpn": vpnOn ? @YES : @NO, @"seen": seen});
}

#pragma mark - [patch] importVideo

// [patch] Bam nut co MOT trong cac nhan `labels` tren alert/hop thoai hien tai.
// QUAN TRONG: cac hop thoai xin-quyen/xac-nhan cua Photos (Add to Photos,
// "delete this video?") do SPRINGBOARD (app he thong) trinh bay, KHONG thuoc
// app dang mo -> phai do tren CA fb_systemApplication LAN fb_activeApplication,
// tren ca alerts[] lan buttons[] (co ban iOS dat nut trong springboard.buttons).
// Tra YES neu vua bam duoc mot nut.
+ (BOOL)fb_tapButtonLabels:(NSArray<NSString *> *)labels
{
  @try {
    // Cac hop thoai co the do: SpringBoard, CHINH app WDA Runner (nguoi goi
    // PhotoKit -> alert xac nhan xoa do no trinh bay), hoac app dang mo.
    NSMutableArray<XCUIApplication *> *apps = [NSMutableArray array];
    XCUIApplication *sys = XCUIApplication.fb_systemApplication;   // SpringBoard
    if (nil != sys) { [apps addObject:sys]; }
    XCUIApplication *selfApp = [[XCUIApplication alloc] init];     // WDA Runner
    if (nil != selfApp) { [apps addObject:selfApp]; }
    XCUIApplication *act = XCUIApplication.fb_activeApplication;
    if (nil != act && ![apps containsObject:act]) { [apps addObject:act]; }

    // Khop nut theo NHAN (label) hoac tieu de (title) - bat ke identifier.
    NSPredicate *pred = [NSPredicate predicateWithFormat:
      @"label IN %@ OR title IN %@", labels, labels];

    for (XCUIApplication *app in apps) {
      // a) Nut trong ALERT (hop thoai 2 nut: Add to Photos / delete this video)
      XCUIElement *ab = [[app.alerts.buttons matchingPredicate:pred] elementBoundByIndex:0];
      if (ab.exists) { [ab tap]; return YES; }
      // b) Nut trong ACTION SHEET (Allow Full Access / Keep Add Only ...)
      XCUIElement *sb = [[app.sheets.buttons matchingPredicate:pred] elementBoundByIndex:0];
      if (sb.exists) { [sb tap]; return YES; }
      // c) Bat ky nut nao khop nhan (mot so alert he thong nam ngoai alerts[])
      XCUIElement *any = [[app.buttons matchingPredicate:pred] elementBoundByIndex:0];
      if (any.exists) { [any tap]; return YES; }
    }
  } @catch (__unused NSException *ex) {}
  return NO;
}

// [patch] Bam mot lan nut dong y (Allow) tren hop thoai xin quyen Photos.
+ (BOOL)fb_tapAllowOnce
{
  return [self fb_tapButtonLabels:@[
    @"Allow", @"Allow Access to All Photos", @"Allow Full Access",
    @"OK", @"Cho phép", @"Cho phep",
  ]];
}

+ (id<FBResponsePayload>)handleImportVideo:(FBRouteRequest *)request
{
  NSString *b64 = request.arguments[@"data"];
  if (![b64 isKindOfClass:NSString.class] || 0 == b64.length) {
    return FBResponseWithObject(@{@"imported": @NO, @"error": @"missing data (base64 video)"});
  }
  NSData *videoData = [[NSData alloc] initWithBase64EncodedString:b64
                                                          options:NSDataBase64DecodingIgnoreUnknownCharacters];
  if (nil == videoData || 0 == videoData.length) {
    return FBResponseWithObject(@{@"imported": @NO, @"error": @"base64 decode failed"});
  }

  NSString *ext = request.arguments[@"ext"];
  if (![ext isKindOfClass:NSString.class] || 0 == ext.length) {
    ext = @"mp4";
  }
  while ([ext hasPrefix:@"."]) {
    ext = [ext substringFromIndex:1];
  }

  NSString *fileName = [NSString stringWithFormat:@"wda_import_%@.%@", NSUUID.UUID.UUIDString, ext];
  NSURL *tmpURL = [NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:fileName]];
  NSError *writeErr = nil;
  if (![videoData writeToURL:tmpURL options:NSDataWritingAtomic error:&writeErr]) {
    return FBResponseWithObject(@{@"imported": @NO,
      @"error": [NSString stringWithFormat:@"write temp failed: %@", writeErr.localizedDescription ?: @"unknown"]});
  }

  NSDate *creationDate = nil;
  NSNumber *ts = request.arguments[@"creationDate"];
  if ([ts isKindOfClass:NSNumber.class]) {
    creationDate = [NSDate dateWithTimeIntervalSince1970:ts.doubleValue];
  }

  PHAuthorizationStatus status;
  if (@available(iOS 14, *)) {
    status = [PHPhotoLibrary authorizationStatusForAccessLevel:PHAccessLevelAddOnly];
  } else {
    status = [PHPhotoLibrary authorizationStatus];
  }

  if (status == PHAuthorizationStatusNotDetermined) {
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block PHAuthorizationStatus answered = PHAuthorizationStatusNotDetermined;
    void (^handler)(PHAuthorizationStatus) = ^(PHAuthorizationStatus st) {
      answered = st;
      dispatch_semaphore_signal(sem);
    };
    if (@available(iOS 14, *)) {
      [PHPhotoLibrary requestAuthorizationForAccessLevel:PHAccessLevelAddOnly handler:handler];
    } else {
      [PHPhotoLibrary requestAuthorization:handler];
    }
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:30];
    while ([deadline timeIntervalSinceNow] > 0) {
      [self fb_tapAllowOnce];
      if (0 == dispatch_semaphore_wait(sem, DISPATCH_TIME_NOW)) { break; }
      [NSThread sleepForTimeInterval:0.4];
    }
    status = answered;
  }

  BOOL authorized = (status == PHAuthorizationStatusAuthorized);
  if (@available(iOS 14, *)) {
    authorized = authorized || (status == PHAuthorizationStatusLimited);
  }
  if (!authorized) {
    [NSFileManager.defaultManager removeItemAtURL:tmpURL error:nil];
    return FBResponseWithObject(@{@"imported": @NO,
      @"error": [NSString stringWithFormat:@"Photos permission not granted (status=%ld)", (long)status]});
  }

  __block NSError *changeErr = nil;
  [PHPhotoLibrary.sharedPhotoLibrary performChangesAndWait:^{
    PHAssetCreationRequest *creationRequest =
      [PHAssetCreationRequest creationRequestForAssetFromVideoAtFileURL:tmpURL];
    if (nil != creationDate) {
      creationRequest.creationDate = creationDate;
    }
  } error:&changeErr];

  [NSFileManager.defaultManager removeItemAtURL:tmpURL error:nil];

  if (nil != changeErr) {
    return FBResponseWithObject(@{@"imported": @NO,
      @"error": changeErr.localizedDescription ?: @"performChanges failed"});
  }
  return FBResponseWithObject(@{@"imported": @YES, @"ext": ext});
}

#pragma mark - [patch] deleteRecentVideos

// [patch] Bam mot lan nut xac nhan XOA tren alert/action-sheet hien tai (neu
// co). Dung ngu canh XCUITest cua caller. Tra YES neu vua bam duoc.
+ (BOOL)fb_tapDeleteOnce
{
  // Uu tien nut xac nhan XOA; kem theo nhan cap quyen (lan dau xoa iOS xin
  // quyen Full Access). Do tren CA SpringBoard lan app hien tai.
  if ([self fb_tapButtonLabels:@[
    @"Delete", @"Delete Video", @"Delete Videos", @"Delete Items", @"Delete Item",
    @"Xóa", @"Xoá", @"Xóa video", @"Xóa Video", @"Xóa mục", @"Remove",
    @"Allow Full Access", @"Allow Access to All Photos", @"Allow", @"OK",
  ]]) {
    return YES;
  }
  // Du phong: nut "Delete N Videos" (so luong doi) -> khop theo CHUOI CON.
  @try {
    NSMutableArray<XCUIApplication *> *apps = [NSMutableArray array];
    XCUIApplication *sys = XCUIApplication.fb_systemApplication;
    if (nil != sys) { [apps addObject:sys]; }
    XCUIApplication *selfApp = [[XCUIApplication alloc] init];
    if (nil != selfApp) { [apps addObject:selfApp]; }
    XCUIApplication *act = XCUIApplication.fb_activeApplication;
    if (nil != act && ![apps containsObject:act]) { [apps addObject:act]; }
    NSPredicate *p = [NSPredicate predicateWithFormat:
      @"label CONTAINS[c] 'Delete' OR label CONTAINS[c] 'Xóa' "
      @"OR title CONTAINS[c] 'Delete' OR title CONTAINS[c] 'Xóa'"];
    for (XCUIApplication *app in apps) {
      // alert -> sheet -> button
      XCUIElement *a = [[app.alerts.buttons matchingPredicate:p] elementBoundByIndex:0];
      if (a.exists) { [a tap]; return YES; }
      XCUIElement *s = [[app.sheets.buttons matchingPredicate:p] elementBoundByIndex:0];
      if (s.exists) { [s tap]; return YES; }
      XCUIElement *b = [[app.buttons matchingPredicate:p] elementBoundByIndex:0];
      if (b.exists) { [b tap]; return YES; }
    }
  } @catch (__unused NSException *ex) {}
  return NO;
}

// [patch] XOA `count` video MOI NHAT (theo creationDate) khoi Thu vien anh.
// Body JSON: {"count": 2}. Tra {"deleted": <so_video_da_xoa>}.
+ (id<FBResponsePayload>)handleDeleteRecentVideos:(FBRouteRequest *)request
{
  NSInteger count = 2;
  NSNumber *cnt = request.arguments[@"count"];
  if ([cnt isKindOfClass:NSNumber.class] && cnt.integerValue > 0) {
    count = cnt.integerValue;
  }

  // Xoa can quyen READ-WRITE (khac importVideo chi can AddOnly).
  PHAuthorizationStatus status;
  if (@available(iOS 14, *)) {
    status = [PHPhotoLibrary authorizationStatusForAccessLevel:PHAccessLevelReadWrite];
  } else {
    status = [PHPhotoLibrary authorizationStatus];
  }
  if (status == PHAuthorizationStatusNotDetermined) {
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block PHAuthorizationStatus answered = PHAuthorizationStatusNotDetermined;
    void (^handler)(PHAuthorizationStatus) = ^(PHAuthorizationStatus st) {
      answered = st; dispatch_semaphore_signal(sem);
    };
    if (@available(iOS 14, *)) {
      [PHPhotoLibrary requestAuthorizationForAccessLevel:PHAccessLevelReadWrite handler:handler];
    } else {
      [PHPhotoLibrary requestAuthorization:handler];
    }
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:30];
    while ([deadline timeIntervalSinceNow] > 0) {
      [self fb_tapDeleteOnce];
      if (0 == dispatch_semaphore_wait(sem, DISPATCH_TIME_NOW)) { break; }
      [NSThread sleepForTimeInterval:0.4];
    }
    status = answered;
  }
  BOOL authorized = (status == PHAuthorizationStatusAuthorized);
  if (@available(iOS 14, *)) {
    authorized = authorized || (status == PHAuthorizationStatusLimited);
  }
  if (!authorized) {
    return FBResponseWithObject(@{@"deleted": @0,
      @"error": [NSString stringWithFormat:@"Photos read-write not granted (status=%ld)", (long)status]});
  }

  // Lay `count` video MOI NHAT theo creationDate giam dan.
  PHFetchOptions *opts = [PHFetchOptions new];
  opts.predicate = [NSPredicate predicateWithFormat:@"mediaType == %d", PHAssetMediaTypeVideo];
  opts.sortDescriptors = @[[NSSortDescriptor sortDescriptorWithKey:@"creationDate" ascending:NO]];
  PHFetchResult<PHAsset *> *res = [PHAsset fetchAssetsWithOptions:opts];
  NSMutableArray<PHAsset *> *toDelete = [NSMutableArray array];
  for (NSInteger i = 0; i < count && i < (NSInteger)res.count; i++) {
    [toDelete addObject:res[(NSUInteger)i]];
  }
  if (0 == toDelete.count) {
    return FBResponseWithObject(@{@"deleted": @0, @"note": @"no video in library"});
  }

  // Xoa: performChanges bat 1 alert xac nhan -> vua doi ket qua vua tu bam Delete.
  __block BOOL success = NO;
  __block NSError *delErr = nil;
  dispatch_semaphore_t sem = dispatch_semaphore_create(0);
  [PHPhotoLibrary.sharedPhotoLibrary performChanges:^{
    [PHAssetChangeRequest deleteAssets:toDelete];
  } completionHandler:^(BOOL ok, NSError *e) {
    success = ok; delErr = e; dispatch_semaphore_signal(sem);
  }];
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:20];
  while ([deadline timeIntervalSinceNow] > 0) {
    [self fb_tapDeleteOnce];
    if (0 == dispatch_semaphore_wait(sem, DISPATCH_TIME_NOW)) { break; }
    [NSThread sleepForTimeInterval:0.3];
  }
  return FBResponseWithObject(@{
    @"deleted": success ? @(toDelete.count) : @0,
    @"error": delErr.localizedDescription ?: @""});
}
'''


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    path = os.path.join(root, TARGET)
    if not os.path.isfile(path):
        print("[patch] LOI: khong thay", path); sys.exit(1)
    with open(path, "r", encoding="utf-8") as fp:
        src = fp.read()
    if "handleDeleteRecentVideos" in src:
        print("[patch] da va (co deleteRecentVideos) -> bo qua"); return
    if "handleImportVideo" in src:
        # File da va ban CU (chua co deleteRecentVideos). Bao nguoi dung checkout
        # ban WebDriverAgent SACH roi va lai de co du ca 2 route.
        print("[patch] LOI: file da va ban cu (thieu deleteRecentVideos). "
              "Hay checkout WebDriverAgent SACH roi chay lai patch."); sys.exit(5)
    if IMPORT_ANCHOR not in src:
        print("[patch] LOI: khong thay anchor import"); sys.exit(2)
    if ROUTE_ANCHOR not in src:
        print("[patch] LOI: khong thay anchor route OPTIONS"); sys.exit(3)
    end_idx = src.rfind("\n@end")
    if end_idx < 0:
        print("[patch] LOI: khong thay @end"); sys.exit(4)
    src = src.replace(IMPORT_ANCHOR, IMPORT_ADD, 1)
    src = src.replace(ROUTE_ANCHOR, ROUTE_ADD, 1)
    end_idx = src.rfind("\n@end")
    src = src[:end_idx] + "\n" + HANDLER + src[end_idx:]
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(src)
    print("[patch] OK -> importVideo + deleteRecentVideos + vpnStatus ->", TARGET)


if __name__ == "__main__":
    main()
