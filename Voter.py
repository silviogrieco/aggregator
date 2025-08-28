class Voter:

    def __init__(self, pub_key):
        self.pub_key = pub_key

    def cast_vote(self,vote):
        return self.pub_key.encrypt(vote)