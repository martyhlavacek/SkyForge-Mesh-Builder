# Bootstrap provenance correction 001

The initial bootstrap instruction contained an incorrect expanded Import Probe binding digest. The accepted source archive itself was not defective. Its binding JSON and an independent recomputation both produce:

`883510570c572ada2166019b356bfbefd3e7053c5074553d1c1dde1234d74ba7`

The Import Probe source archive SHA-256 remains unchanged:

`13d5472ea81079016c8294d0a88685626bc840abe0452d8ffc2e3133aaaa1475`

No product MBS finding is assigned because this was an external bootstrap-instruction transcription error. This correction does not modify either accepted source tree.
