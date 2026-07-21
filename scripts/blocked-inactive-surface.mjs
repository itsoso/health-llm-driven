const surface = process.argv[2] || 'unknown';

console.error(
  `[security] ${surface} is quarantined and is not an approved build or release surface. ` +
  'Complete a dependency/security re-baseline and update the product map before re-enabling it.',
);
process.exit(1);
