import 'dart:async';
import 'dart:js_interop';

/// Geolocalisation navigateur, sans dependance de plugin.
///
/// Cible Chrome, conformement au perimetre du MVP. Sur mobile natif il
/// faudrait passer par geolocator ; l'interface publique resterait identique.
@JS('navigator.geolocation')
external _Geolocation? get _geolocation;

@JS()
@staticInterop
class _Geolocation {}

extension on _Geolocation {
  external void getCurrentPosition(
    JSFunction success,
    JSFunction error,
    JSObject options,
  );
}

@JS()
@staticInterop
class _Position {}

extension on _Position {
  external _Coords get coords;
}

@JS()
@staticInterop
class _Coords {}

extension on _Coords {
  external double get latitude;
  external double get longitude;
}

/// Position obtenue, ou null si refusee ou indisponible.
typedef LatLonResult = ({double lat, double lon})?;

class Geolocation {
  const Geolocation();

  /// Demande la position au navigateur. Ne leve jamais : retourne null si
  /// l'utilisateur refuse, si le delai expire ou si l'API est absente.
  Future<LatLonResult> current({
    Duration timeout = const Duration(seconds: 8),
  }) async {
    final geo = _geolocation;
    if (geo == null) return null;

    final completer = Completer<LatLonResult>();

    void finish(LatLonResult value) {
      if (!completer.isCompleted) completer.complete(value);
    }

    try {
      geo.getCurrentPosition(
        ((JSAny position) {
          final coords = (position as _Position).coords;
          finish((lat: coords.latitude, lon: coords.longitude));
        }).toJS,
        ((JSAny _) => finish(null)).toJS,
        {
          'enableHighAccuracy': true,
          'timeout': timeout.inMilliseconds,
          'maximumAge': 0,
        }.jsify() as JSObject,
      );
    } catch (_) {
      return null;
    }

    return completer.future.timeout(
      timeout + const Duration(seconds: 2),
      onTimeout: () => null,
    );
  }
}
