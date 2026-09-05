# Structure provenance

Source mesh records include dataset, source asset, source revision/input identity,
chunk SHA-256, original ontology term, donor, donor sex, reference sex, geometry
category, licence, transform chain and confidence/review state.

HRA reference sex is female; individual component donor sex is unresolved.
BodyParts3D is a male reference. TCIA subject 003 is verified female from the
corrected clinical spreadsheet. Denver meshes come from the single female VHF donor
and keep archive member, CRC and STL hash; their frame is the aligned VHF image
frame, recorded as `native-VHF-image-frame` because no canonical VHF space is defined yet. BMFToolkit distinguishes right segmentations from
mirrored left anatomy and a symmetrized sacrum.

The source records have no VHF registration. Composite records identify the
experimental regional/global transformation and separately retain the original
source chunk hash. Derived chunk hashes identify the transformed output.

Source geometry checks and the source anatomical review status are distinct.
Confidence remains null. No numeric confidence has been invented from a visually
plausible rendering or from a successful file-integrity check.
