import logging

from flask import request
from flask_restplus import Resource, inputs
from biolink.datamodel.serializers import association
from ontobio.golr.golr_associations import map2slim
from biolink.api.restplus import api
from scigraph.scigraph_util import SciGraph
from biolink import USER_AGENT

log = logging.getLogger(__name__)

ns = api.namespace('bioentityset/slimmer', description='maps a set of entities to a slim')

INVOLVED_IN = 'involved_in'
ACTS_UPSTREAM_OF_OR_WITHIN = 'acts_upstream_of_or_within'

FUNCTION_CATEGORY='function'
PHENOTYPE_CATEGORY='phenotype'
ANATOMY_CATEGORY='anatomy'

parser = api.parser()
parser.add_argument('subject', action='append', help='Entity ids to be examined, e.g. NCBIGene:9342, NCBIGene:7227, NCBIGene:8131, NCBIGene:157570, NCBIGene:51164, NCBIGene:6689, NCBIGene:6387', required=True)
parser.add_argument('slim', action='append', help='Map objects up (slim) to a higher level category. Value can be ontology class ID (IMPLEMENTED) or subset ID (TODO)', required=True)
parser.add_argument('exclude_automatic_assertions', type=inputs.boolean, default=False, help='If set, excludes associations that involve IEAs (ECO:0000501)')
parser.add_argument('rows', type=int, required=False, default=100, help='number of rows')
parser.add_argument('start', type=int, required=False, help='beginning row')
parser.add_argument('relationship_type', choices=[INVOLVED_IN, ACTS_UPSTREAM_OF_OR_WITHIN], default=ACTS_UPSTREAM_OF_OR_WITHIN, help="relationship type ('{}' or '{}')".format(INVOLVED_IN, ACTS_UPSTREAM_OF_OR_WITHIN))

@ns.route('/<category>')
@api.param('category', 'category type', enum=[FUNCTION_CATEGORY, PHENOTYPE_CATEGORY, ANATOMY_CATEGORY])
class EntitySetSlimmer(Resource):

    @api.expect(parser)
    def get(self, category):
        """
        Summarize a set of objects
        """
        args = parser.parse_args()
        slim = args.get('slim')
        del args['slim']
        subjects = args.get('subject')
        del args['subject']
        # Note that GO currently uses UniProt as primary ID for some sources: https://github.com/biolink/biolink-api/issues/66
        # https://github.com/monarch-initiative/dipper/issues/461

        sg_dev = SciGraph(url='https://scigraph-data-dev.monarchinitiative.org/scigraph/')

        subjects = [x.replace('WormBase:', 'WB:') if 'WormBase:' in x else x for x in subjects]
        slimmer_subjects = []
        if category == FUNCTION_CATEGORY:
            # get proteins for a gene only when the category is 'function'
            for s in subjects:
                if 'HGNC:' in s or 'NCBIGene:' in s or 'ENSEMBL:' in s:
                    prots = sg_dev.gene_to_uniprot_proteins(s)
                    if len(prots) == 0:
                        prots = [s]
                    slimmer_subjects += prots
                else:
                    slimmer_subjects.append(s)
        else:
            slimmer_subjects = subjects

        if category == ANATOMY_CATEGORY:
            category = 'anatomical entity'

        results = map2slim(
            subjects=slimmer_subjects,
            slim=slim,
            object_category=category,
            user_agent=USER_AGENT,
            **args
        )

        # To the fullest extent possible return HGNC ids
        checked = {}
        for result in results:
            for association in result['assocs']:
                taxon = association['subject']['taxon']['id']
                proteinId = association['subject']['id']
                if taxon == 'NCBITaxon:9606' and proteinId.startswith('UniProtKB:'):
                    if checked.get(proteinId) == None:
                        genes = sg_dev.uniprot_protein_to_genes(proteinId)
                        for gene in genes:
                            if gene.startswith('HGNC'):
                                association['subject']['id'] = gene
                                checked[proteinId] = gene
                    else:
                        association['subject']['id'] = checked[proteinId]
        return results
