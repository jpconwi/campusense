import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nemsai/widgets/skeleton.dart';

void main() {
  testWidgets('skeletons render without errors', (tester) async {
    for (final w in const [HomeSkeleton(), ListSkeleton(), FormSkeleton(), ChatSkeleton()]) {
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: w)));
      await tester.pump(const Duration(milliseconds: 300));
    }
  });
}
