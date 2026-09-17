import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

import '../domain/models.dart';

/// Charge les places depuis l'asset local.
///
/// Choix delibere : les places viennent du bundle embarque, pas de l'API.
/// La carte s'affiche donc TOUJOURS, meme si le serveur Python est arrete.
/// Seuls les itineraires dependent du backend.
class SpotRepository {
  SpotRepository({this.assetPath = 'assets/data/halifax_bundle.json'});

  final String assetPath;
  List<ParkingSpot>? _cache;
  List<ParkingRestriction> _restrictions = const [];

  /// Troncons a permis, disponibles apres load().
  List<ParkingRestriction> get restrictions => _restrictions;

  Future<List<ParkingSpot>> load() async {
    final cached = _cache;
    if (cached != null) return cached;

    final json = jsonDecode(await rootBundle.loadString(assetPath))
        as Map<String, dynamic>;
    final occupancy = json['occupancy'] as Map<String, dynamic>? ?? {};

    final spots = (json['spots'] as List)
        .map((e) => e as Map<String, dynamic>)
        .where((e) => e['status'] == 'installed')
        .map((e) => ParkingSpot.fromBundle(
              e,
              occupancy[e['id']] as List<dynamic>?,
            ))
        .toList(growable: false);

    _restrictions = ((json['restrictions'] as List?) ?? const [])
        .map((e) => ParkingRestriction.fromJson(e as Map<String, dynamic>))
        .toList(growable: false);

    _cache = spots;
    return spots;
  }
}
