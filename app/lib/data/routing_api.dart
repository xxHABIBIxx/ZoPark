import 'dart:convert';

import 'package:http/http.dart' as http;

import '../domain/models.dart';

/// Client de l'API de routage Python (FastAPI + OSMnx + Random Forest + A*).
///
/// Si le serveur est injoignable, retourne un RouteResult degrade contenant un
/// trace a vol d'oiseau. L'application reste utilisable et le dit clairement,
/// plutot que d'afficher une erreur au milieu d'une demonstration.
class RoutingApi {
  RoutingApi({this.baseUrl = 'http://127.0.0.1:8000'});

  final String baseUrl;

  Future<RouteResult> fetchRoute({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) async {
    try {
      final response = await http
          .post(
            Uri.parse('$baseUrl/route'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({
              'from_lat': fromLat,
              'from_lon': fromLon,
              'to_lat': toLat,
              'to_lon': toLon,
            }),
          )
          .timeout(const Duration(seconds: 25));

      if (response.statusCode != 200) {
        return _fallback(
          fromLat, fromLon, toLat, toLon,
          'Le serveur a repondu ${response.statusCode}.',
        );
      }

      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return RouteResult(
        classic: RouteLeg.fromJson(json['classic'] as Map<String, dynamic>?),
        zopark: RouteLeg.fromJson(json['zopark'] as Map<String, dynamic>?),
        identical: json['routes_identical'] as bool? ?? false,
        inference: (json['inference'] as Map<String, dynamic>?) ?? const {},
      );
    } catch (e) {
      return _fallback(fromLat, fromLon, toLat, toLon,
          'Serveur de routage injoignable.');
    }
  }

  /// Trace direct, affiche en pointille : honnete sur ce qui est calcule.
  RouteResult _fallback(
      double fromLat, double fromLon, double toLat, double toLon, String why) {
    final distance = haversineMeters(fromLat, fromLon, toLat, toLon);
    return RouteResult(
      degradedReason: why,
      zopark: RouteLeg(
        points: [(lat: fromLat, lon: fromLon), (lat: toLat, lon: toLon)],
        distanceMeters: distance,
        driveMinutes: (distance / 1000 / 30 * 60).ceil().clamp(1, 999),
        avgOccupancy: 0.0,
      ),
    );
  }
}


/// Disponibilite predite pour chaque place, indexee par identifiant.
class AvailabilityMap {
  const AvailabilityMap(
    this.byId, {
    this.reachable = true,
    this.generatedAt,
  });

  final Map<String, double> byId;

  /// Faux quand le serveur n'a pas repondu : l'app le signale a l'ecran.
  final bool reachable;

  /// Horodatage renvoye par le serveur : c'est lui qui fait autorite sur le
  /// contexte temporel, pas l'horloge du navigateur.
  final DateTime? generatedAt;

  double? freeChance(String id) => byId[id];

  static const empty = AvailabilityMap({}, reachable: false);
}

extension AvailabilityCall on RoutingApi {
  /// Interroge le modele pour la disponibilite de toutes les places.
  ///
  /// Aucun parametre : l'heure et le jour sont lus sur l'horloge du serveur.
  /// L'utilisateur ne pilote pas le contexte, le modele decide seul.
  Future<AvailabilityMap> fetchAvailability() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/availability'))
          .timeout(const Duration(seconds: 20));

      if (response.statusCode != 200) return AvailabilityMap.empty;

      final json = jsonDecode(response.body) as Map<String, dynamic>;
      final map = <String, double>{};
      for (final entry in (json['spots'] as List)) {
        final m = entry as Map<String, dynamic>;
        map[m['id'] as String] = (m['free'] as num).toDouble();
      }
      return AvailabilityMap(
        map,
        generatedAt: DateTime.tryParse(json['generated_at'] as String? ?? ''),
      );
    } catch (_) {
      return AvailabilityMap.empty;
    }
  }
}
