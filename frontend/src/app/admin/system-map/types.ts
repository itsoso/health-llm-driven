export type SystemMapEntityKind = 'component' | 'surface' | 'api' | 'resource' | 'job';
export type SystemMapCoverage = 'complete' | 'partial' | 'declaration';

export interface SystemMapSource {
  type: 'code' | 'generated' | 'declaration';
  path: string;
  symbol?: string;
}

export interface SystemMapEntity {
  id: string;
  kind: SystemMapEntityKind;
  name: string;
  coverage: SystemMapCoverage;
  source: SystemMapSource;
  description?: string;
  owner?: string;
  domain?: string;
  lifecycle?: string;
  trust_boundary?: string;
  tags?: string[];
  data_classes?: Array<'L1' | 'L2' | 'L3' | 'L4'>;
}

export interface SystemMapRelation {
  from: string;
  type: string;
  to: string;
  coverage: SystemMapCoverage;
  source: SystemMapSource;
  flows?: string[];
}

export interface SystemMapData {
  schema_version: '2.0';
  entities: SystemMapEntity[];
  relations: SystemMapRelation[];
  coverage: Record<string, {
    source: string;
    status: SystemMapCoverage;
    limitations?: string;
  }>;
  counts: Record<string, number>;
}
