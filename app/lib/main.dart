import 'package:flutter/material.dart';

import 'core/design.dart';
import 'data/geolocation.dart';
import 'data/routing_api.dart';
import 'data/spot_repository.dart';
import 'state/app_state.dart';
import 'ui/map_screen.dart';

void main() => runApp(const ZoParkApp());

class ZoParkApp extends StatefulWidget {
  const ZoParkApp({super.key});

  @override
  State<ZoParkApp> createState() => _ZoParkAppState();
}

class _ZoParkAppState extends State<ZoParkApp> {
  late final AppState _state = AppState(SpotRepository(), RoutingApi(), const Geolocation());

  @override
  void initState() {
    super.initState();
    _state.initialise();
  }

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: "ZoPark — Halifax",
        debugShowCheckedModeBanner: false,
        theme: Zo.theme(),
        home: MapScreen(state: _state),
      );
}
