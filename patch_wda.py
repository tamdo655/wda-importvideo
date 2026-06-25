#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vá WebDriverAgent: thêm route POST /wda/importVideo để ghi video THẲNG vào
Thư viện ảnh (Photos) qua PHPhotoLibrary — đúng cách xiaowei làm.

Chạy trong GitHub Actions SAU khi checkout appium/WebDriverAgent và TRƯỚC khi
xcodebuild:   python3 patch_wda.py <đường_dẫn_thư_mục_WDA>

Chỉ sửa 1 file có sẵn (WebDriverAgentLib/Commands/FBCustomCommands.m) nên KHÔNG
cần đụng tới project.pbxproj. Idempotent: chạy lại nhiều lần không hỏng.
"""
import os
import sys

TARGET = os.path.join("WebDriverAgentLib", "Commands", "FBCustomCommands.m")

IMPORT_ANCHOR = '#import "FBCustomCommands.h"'
IMPORT_ADD = '#import "FBCustomCommands.h"\n@import Photos;  // [patch] importVideo -> PHPhotoLibrary'

# Dòng route cuối cùng (OPTIONS) ổn định qua mọi phiên bản WDA -> chèn route mới
# ngay trước nó.
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

+ (id<FBResponsePayload>)handleImportVideo:(FBRouteRequest *)request
{
  NSString *b64 = request.arguments[@"data"];
  if (![b64 isKindOfClass:NSString.class] || 0 == b64.length) {
    return FBResponseWithObject(@{@"imported": @NO, @"error": @"missing 'data' (base64 video)"});
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

  // Ngày tạo (unix giây) -> giữ ĐÚNG THỨ TỰ trong app Ảnh (Ảnh xếp theo ngày).
  NSDate *creationDate = nil;
  NSNumber *ts = request.arguments[@"creationDate"];
  if ([ts isKindOfClass:NSNumber.class]) {
    creationDate = [NSDate dateWithTimeIntervalSince1970:ts.doubleValue];
  }

  // Xin quyền add-only (đồng bộ). Lần đầu sẽ hiện hộp thoại -> bấm Cho phép 1 lần.
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
        print("[patch] LỖI: không thấy", path)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as fp:
        src = fp.read()

    if "handleImportVideo" in src:
        print("[patch] đã vá rồi -> bỏ qua")
        return

    if IMPORT_ANCHOR not in src:
        print("[patch] LỖI: không thấy anchor import")
        sys.exit(2)
    if ROUTE_ANCHOR not in src:
        print("[patch] LỖI: không thấy anchor route OPTIONS")
        sys.exit(3)
    end_idx = src.rfind("\n@end")
    if end_idx < 0:
        print("[patch] LỖI: không thấy @end")
        sys.exit(4)

    src = src.replace(IMPORT_ANCHOR, IMPORT_ADD, 1)
    src = src.replace(ROUTE_ANCHOR, ROUTE_ADD, 1)
    end_idx = src.rfind("\n@end")
    src = src[:end_idx] + "\n" + HANDLER + src[end_idx:]

    with open(path, "w", encoding="utf-8") as fp:
        fp.write(src)
    print("[patch] OK -> đã thêm /wda/importVideo vào", TARGET)


if __name__ == "__main__":
    main()
