#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Va WebDriverAgent: them route POST /wda/importVideo de ghi video THANG vao
Thu vien anh (Photos) qua PHPhotoLibrary.

PHIEN BAN 4 (29/06/2026): tu bam "Allow" NGAY TREN LUONG XU LY CUA HANDLER
(dung ngu canh XCUITest - giong het khi WDA xu ly /alert/accept). Cac ban truoc
bam o global queue nen XCUITest khong thuc thi tap -> popup dung im. Ban nay
goi requestAuthorization (hien popup) roi VONG LAP DONG BO ngay tren queue cua
handler de FBAlert bam Allow, cho toi khi co quyen hoac het 30s. KHONG cham phone.
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
    '    ' + ROUTE_ANCHOR
)

HANDLER = r'''
#pragma mark - [patch] importVideo

// [patch] Bam mot lan cac nut dong y tren alert hien tai (neu co). Chay TREN
// queue cua caller (dung ngu canh XCUITest). Tra YES neu vua bam duoc.
+ (BOOL)fb_tapAllowOnce
{
  NSArray<NSString *> *labels = @[
    @"Allow", @"OK", @"Cho phép", @"Cho phep", @"Allow Access to All Photos",
  ];
  @try {
    XCUIApplication *app = XCUIApplication.fb_activeApplication;
    if (nil == app) { return NO; }
    FBAlert *alert = [FBAlert alertWithApplication:app];
    if (!alert.isPresent) { return NO; }
    NSError *err = nil;
    for (NSString *name in labels) {
      err = nil;
      if ([alert clickAlertButton:name error:&err]) { return YES; }
    }
    err = nil;
    if ([alert acceptWithError:&err]) { return YES; }
  } @catch (__unused NSException *ex) {}
  return NO;
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

  // Trang thai quyen hien tai.
  PHAuthorizationStatus status;
  if (@available(iOS 14, *)) {
    status = [PHPhotoLibrary authorizationStatusForAccessLevel:PHAccessLevelAddOnly];
  } else {
    status = [PHPhotoLibrary authorizationStatus];
  }

  // [patch] Neu CHUA quyet dinh: hien popup roi TU BAM Allow ngay tren queue nay
  // (dung ngu canh XCUITest) -> khong can cham phone, khong deadlock.
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
'''


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    path = os.path.join(root, TARGET)
    if not os.path.isfile(path):
        print("[patch] LOI: khong thay", path); sys.exit(1)
    with open(path, "r", encoding="utf-8") as fp:
        src = fp.read()
    if "handleImportVideo" in src:
        print("[patch] da va roi -> bo qua"); return
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
    print("[patch] OK -> importVideo + auto-Allow dong bo (FBAlert) ->", TARGET)


if __name__ == "__main__":
    main()
