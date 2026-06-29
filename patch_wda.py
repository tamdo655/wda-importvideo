#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Va WebDriverAgent: them route POST /wda/importVideo de ghi video THANG vao
Thu vien anh (Photos) qua PHPhotoLibrary.

PHIEN BAN 2 (29/06/2026): tu bam nut "Allow" ngay BEN TRONG WDA.
  Ly do: ban cu cho luong Python bam Allow qua HTTP /alert/accept, nhung
  handleImportVideo dang CHAN luong HTTP server cua WDA (semaphore) de cho quyen
  -> request /alert/accept khong bao gio chay duoc (deadlock) -> van phai bam tay.
  Ban nay cho WDA tu go vao nut Allow cua hop thoai SpringBoard o 1 luong nen
  song song voi requestAuthorization, nen KHONG can cham vao dien thoai. Ho tro
  ca nhan tieng Anh ("Allow") lan tieng Viet ("Cho phep").

Chay trong GitHub Actions SAU khi checkout appium/WebDriverAgent va TRUOC khi
xcodebuild:   python3 patch_wda.py <duong_dan_thu_muc_WDA>
"""
import os
import sys

TARGET = os.path.join("WebDriverAgentLib", "Commands", "FBCustomCommands.m")

IMPORT_ANCHOR = '#import "FBCustomCommands.h"'
IMPORT_ADD = '#import "FBCustomCommands.h"\n@import Photos;  // [patch] importVideo -> PHPhotoLibrary'

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

// [patch] Tu dong bam nut "Allow" tren hop thoai xin quyen Anh cua SpringBoard.
// Ho tro nhan dien nut theo ca tieng Anh va tieng Viet.
+ (void)fb_autoAllowPhotosAlert:(NSTimeInterval)seconds
{
  NSArray<NSString *> *labels = @[
    @"Allow",
    @"OK",
    @"Cho phép",
    @"Cho phep",
    @"Allow Access to All Photos",
    @"Cho phép truy cập tất cả ảnh",
    @"Cho phép Truy cập vào Tất cả Ảnh",
  ];
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:seconds];
  while ([deadline timeIntervalSinceNow] > 0) {
    @try {
      XCUIApplication *sb = XCUIApplication.fb_systemApplication;
      for (NSString *label in labels) {
        XCUIElement *btn = sb.buttons[label];
        if (btn.exists) {
          [btn tap];
          return;
        }
      }
    } @catch (__unused NSException *ex) {
    }
    [NSThread sleepForTimeInterval:0.4];
  }
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

  // [patch] Neu quyen Anh CHUA duoc quyet dinh -> khoi dong luong nen tu bam Allow.
  PHAuthorizationStatus preStatus;
  if (@available(iOS 14, *)) {
    preStatus = [PHPhotoLibrary authorizationStatusForAccessLevel:PHAccessLevelAddOnly];
  } else {
    preStatus = [PHPhotoLibrary authorizationStatus];
  }
  if (preStatus == PHAuthorizationStatusNotDetermined) {
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
      [self fb_autoAllowPhotosAlert:25.0];
    });
  }

  __block PHAuthorizationStatus authStatus = PHAuthorizationStatusNotDetermined;
  dispatch_semaphore_t sem = dispatch_semaphore_create(0);
  if (@available(iOS 14, *)) {
    [PHPhotoLibrary requestAuthorizationForAccessLevel:PHAccessLevelAddOnly
                                               handler:^(PHAuthorizationStatus status) {
      authStatus = status;
      dispatch_semaphore_signal(sem);
    }];
  } else {
    [PHPhotoLibrary requestAuthorization:^(PHAuthorizationStatus status) {
      authStatus = status;
      dispatch_semaphore_signal(sem);
    }];
  }
  dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(60 * NSEC_PER_SEC)));

  BOOL authorized = (authStatus == PHAuthorizationStatusAuthorized);
  if (@available(iOS 14, *)) {
    authorized = authorized || (authStatus == PHAuthorizationStatusLimited);
  }
  if (!authorized) {
    [NSFileManager.defaultManager removeItemAtURL:tmpURL error:nil];
    return FBResponseWithObject(@{@"imported": @NO,
      @"error": [NSString stringWithFormat:@"Photos permission not granted (status=%ld)", (long)authStatus]});
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
        print("[patch] LOI: khong thay", path)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as fp:
        src = fp.read()
    if "handleImportVideo" in src:
        print("[patch] da va roi -> bo qua")
        return
    if IMPORT_ANCHOR not in src:
        print("[patch] LOI: khong thay anchor import")
        sys.exit(2)
    if ROUTE_ANCHOR not in src:
        print("[patch] LOI: khong thay anchor route OPTIONS")
        sys.exit(3)
    end_idx = src.rfind("\n@end")
    if end_idx < 0:
        print("[patch] LOI: khong thay @end")
        sys.exit(4)
    src = src.replace(IMPORT_ANCHOR, IMPORT_ADD, 1)
    src = src.replace(ROUTE_ANCHOR, ROUTE_ADD, 1)
    end_idx = src.rfind("\n@end")
    src = src[:end_idx] + "\n" + HANDLER + src[end_idx:]
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(src)
    print("[patch] OK -> da them /wda/importVideo (tu bam Allow EN+VI) vao", TARGET)


if __name__ == "__main__":
    main()
