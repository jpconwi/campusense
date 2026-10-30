/// skeleton.dart - shimmer placeholders that mirror the real layouts while data loads.
/// (Port of the website's Skeletons.jsx.)
library;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Wraps a tree of [Sk] blocks and sweeps a light band across all of them at once.
class Shimmer extends StatefulWidget {
  const Shimmer({super.key, required this.child});
  final Widget child;

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _SlideGradient extends GradientTransform {
  const _SlideGradient(this.t);
  final double t;
  @override
  Matrix4? transform(Rect bounds, {TextDirection? textDirection}) =>
      Matrix4.translationValues(bounds.width * (t * 2 - 1), 0, 0);
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1300))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Loading',
      child: ExcludeSemantics(
        child: AnimatedBuilder(
          animation: _c,
          child: widget.child,
          builder: (context, child) => ShaderMask(
            blendMode: BlendMode.srcATop,
            shaderCallback: (bounds) => LinearGradient(
              colors: const [C.skBase, C.skHigh, C.skBase],
              stops: const [0.25, 0.5, 0.75],
              transform: _SlideGradient(_c.value),
            ).createShader(bounds),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// One grey block.
class Sk extends StatelessWidget {
  const Sk({super.key, this.w, this.h = 14, this.r = 6, this.onDark = false});
  final double? w;
  final double h;
  final double r;
  final bool onDark;

  @override
  Widget build(BuildContext context) => Container(
        width: w,
        height: h,
        decoration: BoxDecoration(
          color: onDark ? Colors.white24 : C.skBase,
          borderRadius: BorderRadius.circular(r),
        ),
      );
}

class _SkCard extends StatelessWidget {
  const _SkCard({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: C.line),
        ),
        child: child,
      );
}

/// Dashboard shape: hero banner + tiles.
class HomeSkeleton extends StatelessWidget {
  const HomeSkeleton({super.key, this.tiles = 5});
  final int tiles;
  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(color: C.blue, borderRadius: BorderRadius.circular(18)),
            child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Sk(h: 12, w: 100, onDark: true),
              SizedBox(height: 12),
              Sk(h: 30, w: 220, r: 8, onDark: true),
              SizedBox(height: 10),
              Sk(h: 14, w: 180, onDark: true),
              SizedBox(height: 18),
              Row(children: [
                Sk(h: 42, w: 130, r: 12, onDark: true),
                SizedBox(width: 10),
                Sk(h: 42, w: 120, r: 12, onDark: true),
              ]),
            ]),
          ),
          const SizedBox(height: 16),
          for (var i = 0; i < tiles; i++) ...[
            const _SkCard(
              child: Row(children: [
                Sk(h: 46, w: 46, r: 13),
                SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Sk(h: 15, w: 130),
                    SizedBox(height: 8),
                    Sk(h: 12),
                  ]),
                ),
              ]),
            ),
            const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

/// List of record cards (My Concerns / Reports / Feedback / Reservations / Faculty).
class ListSkeleton extends StatelessWidget {
  const ListSkeleton({super.key, this.rows = 4, this.heading = true});
  final int rows;
  final bool heading;
  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          if (heading) ...[
            const Sk(h: 28, w: 200, r: 8),
            const SizedBox(height: 10),
            const Sk(h: 13),
            const SizedBox(height: 6),
            const Sk(h: 13, w: 240),
            const SizedBox(height: 16),
            const Sk(h: 48, r: 12),
            const SizedBox(height: 22),
          ],
          for (var i = 0; i < rows; i++) ...[
            _SkCard(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  const Sk(h: 16, w: 140),
                  const Spacer(),
                  Sk(h: 22, w: 64 + (i % 2) * 14, r: 999),
                ]),
                const SizedBox(height: 14),
                const Sk(h: 12),
                const SizedBox(height: 8),
                Sk(h: 12, w: 200 - (i % 3) * 30),
                const SizedBox(height: 8),
                const Sk(h: 12, w: 120),
              ]),
            ),
            const SizedBox(height: 12),
          ],
        ],
      ),
    );
  }
}

/// Form shape.
class FormSkeleton extends StatelessWidget {
  const FormSkeleton({super.key, this.fields = 5});
  final int fields;
  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          const Sk(h: 26, w: 180, r: 8),
          const SizedBox(height: 18),
          for (var i = 0; i < fields; i++) ...[
            const Sk(h: 12, w: 100),
            const SizedBox(height: 8),
            Sk(h: i == 2 ? 90 : 48, r: 10),
            const SizedBox(height: 16),
          ],
          const Sk(h: 48, r: 12),
        ],
      ),
    );
  }
}

/// Chat shape: bubbles alternating left / right.
class ChatSkeleton extends StatelessWidget {
  const ChatSkeleton({super.key});
  @override
  Widget build(BuildContext context) {
    Widget bubble(bool mine, double w, int lines) => Align(
          alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            width: w,
            margin: const EdgeInsets.only(bottom: 14),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: C.line),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              for (var i = 0; i < lines; i++) ...[
                Sk(h: 12, w: i == lines - 1 ? w * 0.5 : null),
                if (i != lines - 1) const SizedBox(height: 8),
              ],
            ]),
          ),
        );
    return Shimmer(
      child: ListView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [bubble(true, 190, 1), bubble(false, 290, 4), bubble(true, 220, 2), bubble(false, 270, 3)],
      ),
    );
  }
}

/// Inline "typing" placeholder inside the chat while the AI answers.
class ReplySkeleton extends StatelessWidget {
  const ReplySkeleton({super.key});
  @override
  Widget build(BuildContext context) => const Shimmer(
        child: SizedBox(
          width: 230,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Sk(h: 12),
            SizedBox(height: 8),
            Sk(h: 12, w: 190),
            SizedBox(height: 8),
            Sk(h: 12, w: 120),
          ]),
        ),
      );
}

/// Shown while the saved sign-in is being checked at app start.
class LaunchSkeleton extends StatelessWidget {
  const LaunchSkeleton({super.key});
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('NEMSAI')),
      body: const HomeSkeleton(),
    );
  }
}
