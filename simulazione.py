import random
from Aggregator import Aggregator
from Authority import Authority
from Voter import Voter


def simulazione():

    while True:

        print("----------------------------Sistema di e-voting con crittografia omomorfica----------------------------")

        aut = Authority()
        pub = aut.getPubKey()

        print("Inserire numero elettori: ")
        n = int(input())

        plain_votes = []
        enc_votes = []

        for i in range(n):
            vote = random.choice([0,1])
            plain_votes.append(vote)
            voter = Voter(pub)

            enc_votes.append(voter.enc(vote))

        aggr = Aggregator(enc_votes)
        print("Plain yes: " + str(sum(plain_votes)))
        print("Plain no: " + str(len(plain_votes) - sum(plain_votes)))
        print("Enc yes: " + str(aut.getPlainVotes(aggr.getEncYes())))
        print("Enc yes: " + str(aut.getPlainVotes(aggr.getEncNo())))