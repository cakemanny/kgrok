

def test_prepare_labels():
    from kgrok.local import prepare_labels

    assert prepare_labels({'app': 'echo'}) == 'app=echo'

    assert prepare_labels({
        'app': 'echo',
        'tier': 'web',
    }) == 'app=echo,tier=web'
